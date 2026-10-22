"""UNO engine. Rules: docs/games/uno.md (challengeable Wild Draw Four, single hand)."""

from __future__ import annotations

import random
from typing import Any

from app.games.base import Action, GameEngine, GameError, GameInfo, Outcome, State, log, who

COLORS = ("red", "yellow", "green", "blue")
HAND_SIZE = 7


def _build_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    def add(color: str | None, kind: str, value: int | None = None) -> None:
        cards.append({"id": len(cards), "color": color, "kind": kind, "value": value})

    for color in COLORS:
        add(color, "number", 0)
        for value in range(1, 10):
            add(color, "number", value)
            add(color, "number", value)
        for kind in ("skip", "reverse", "draw2"):
            add(color, kind)
            add(color, kind)
    for _ in range(4):
        add(None, "wild")
    for _ in range(4):
        add(None, "wild4")
    return cards


CARDS: list[dict[str, Any]] = _build_cards()
assert len(CARDS) == 108


def card_label(card_id: int) -> str:
    card = CARDS[card_id]
    names = {"skip": "Skip", "reverse": "Reverse", "draw2": "Draw Two",
             "wild": "Wild", "wild4": "Wild Draw Four"}
    face = str(card["value"]) if card["kind"] == "number" else names[card["kind"]]
    return face if card["color"] is None else f"{card['color']} {face}"


def is_playable(card_id: int, top_id: int, color: str) -> bool:
    card, top = CARDS[card_id], CARDS[top_id]
    if card["kind"] in ("wild", "wild4") or card["color"] == color:
        return True
    if card["kind"] == "number":
        return top["kind"] == "number" and top["value"] == card["value"]
    return card["kind"] == top["kind"]


class UnoEngine(GameEngine):
    info = GameInfo("uno", "UNO", 2, 4,
                    "Match colours or numbers and be first to empty your hand.")

    # -- setup -----------------------------------------------------------------------

    def new_game(self, players: list[str], rng: random.Random) -> State:
        deck = list(range(len(CARDS)))
        rng.shuffle(deck)
        hands = {p: [deck.pop() for _ in range(HAND_SIZE)] for p in players}
        while CARDS[deck[-1]]["kind"] in ("wild", "wild4"):
            deck.insert(rng.randrange(len(deck)), deck.pop())
        top = deck.pop()
        state: State = {
            "players": list(players),
            "hands": hands,
            "deck": deck,
            "discard": [top],
            "color": CARDS[top]["color"],
            "direction": 1,
            "current": 0,
            "phase": "play",
            "drawn_card": None,
            "pending_wd4": None,
            "uno_vulnerable": None,
            "uno_declared": [],
            "winner": None,
            "win_reason": "",
            "log": [],
        }
        log(state, f"Starting card: {card_label(top)}")
        kind = CARDS[top]["kind"]
        n = len(players)
        if kind == "skip":
            state["current"] = 1 % n
            log(state, f"{who(players[0])} is skipped")
        elif kind == "reverse":
            state["direction"] = -1
            state["current"] = n - 1
            log(state, "Direction reversed")
        elif kind == "draw2":
            self._draw(state, players[0], 2, rng)
            state["current"] = 1 % n
            log(state, f"{who(players[0])} draws 2 and is skipped")
        return state

    # -- helpers ---------------------------------------------------------------------

    @staticmethod
    def _current(state: State) -> str:
        return state["players"][state["current"]]

    @staticmethod
    def _offset(state: State, steps: int) -> int:
        return (state["current"] + steps * state["direction"]) % len(state["players"])

    def _advance(self, state: State, steps: int = 1) -> None:
        state["current"] = self._offset(state, steps)
        state["phase"] = "play"
        state["drawn_card"] = None

    def _draw(self, state: State, player: str, count: int, rng: random.Random) -> list[int]:
        drawn: list[int] = []
        for _ in range(count):
            if not state["deck"]:
                if len(state["discard"]) <= 1:
                    break
                top = state["discard"].pop()
                state["deck"] = state["discard"]
                rng.shuffle(state["deck"])
                state["discard"] = [top]
                log(state, "The discard pile was reshuffled into the deck")
            drawn.append(state["deck"].pop())
        state["hands"][player].extend(drawn)
        self._refresh_uno(state, player)
        return drawn

    @staticmethod
    def _refresh_uno(state: State, player: str) -> None:
        if len(state["hands"][player]) != 1:
            if player in state["uno_declared"]:
                state["uno_declared"].remove(player)
            if state["uno_vulnerable"] == player:
                state["uno_vulnerable"] = None

    # -- actions ---------------------------------------------------------------------

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        kind = action["type"]
        if kind == "uno":
            return self._declare(state, player)
        if kind == "catch":
            return self._catch(state, player, action, rng)
        if player != self._current(state):
            raise GameError("It is not your turn")
        # The next player's turn action closes the window for catching a missed UNO.
        if state["uno_vulnerable"] not in (None, player):
            state["uno_vulnerable"] = None
        handlers = {"play": self._play, "draw": self._draw_action, "pass": self._pass,
                    "accept": self._accept, "challenge": self._challenge}
        handler = handlers.get(kind)
        if handler is None:
            raise GameError("Unknown action")
        handler(state, player, action, rng)

    def _play(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] not in ("play", "drawn"):
            raise GameError("Respond to the Wild Draw Four first")
        card_id = action.get("card")
        hand = state["hands"][player]
        if not isinstance(card_id, int) or isinstance(card_id, bool) or card_id not in hand:
            raise GameError("That card is not in your hand")
        if state["phase"] == "drawn" and card_id != state["drawn_card"]:
            raise GameError("After drawing you may only play the card you drew")
        top = state["discard"][-1]
        if not is_playable(card_id, top, state["color"]):
            raise GameError(f"{card_label(card_id)} cannot be played on {card_label(top)}")
        card = CARDS[card_id]
        if card["color"] is None:
            color = action.get("color")
            if color not in COLORS:
                raise GameError("Choose a colour for the wild card")
        else:
            color = card["color"]

        previous_color = state["color"]
        guilty = card["kind"] == "wild4" and any(
            CARDS[c]["color"] == previous_color for c in hand if c != card_id)
        hand.remove(card_id)
        state["discard"].append(card_id)
        state["color"] = color
        log(state, f"{who(player)} played {card_label(card_id)}"
            + (f" and chose {color}" if card["color"] is None else ""))

        if not hand:
            state["winner"] = player
            state["win_reason"] = "Emptied their hand"
            log(state, f"{who(player)} played their last card and wins")
            return
        if len(hand) == 1:
            if action.get("uno") is True:
                self._mark_declared(state, player)
            else:
                state["uno_vulnerable"] = player
        else:
            self._refresh_uno(state, player)

        n = len(state["players"])
        effect = card["kind"]
        if effect == "skip":
            log(state, f"{who(state['players'][self._offset(state, 1)])} is skipped")
            self._advance(state, 2)
        elif effect == "reverse":
            state["direction"] *= -1
            log(state, "Direction reversed")
            self._advance(state, 2 if n == 2 else 1)
        elif effect == "draw2":
            victim = state["players"][self._offset(state, 1)]
            self._draw(state, victim, 2, rng)
            log(state, f"{who(victim)} draws 2 and is skipped")
            self._advance(state, 2)
        elif effect == "wild4":
            self._advance(state, 1)
            target = self._current(state)
            state["phase"] = "challenge"
            state["pending_wd4"] = {"by": player, "target": target, "guilty": guilty}
        else:
            self._advance(state, 1)

    def _draw_action(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "play":
            raise GameError("You cannot draw now")
        drawn = self._draw(state, player, 1, rng)
        if not drawn:
            log(state, f"{who(player)} could not draw (no cards left) and passes")
            self._advance(state, 1)
            return
        log(state, f"{who(player)} drew a card")
        if is_playable(drawn[0], state["discard"][-1], state["color"]):
            state["phase"] = "drawn"
            state["drawn_card"] = drawn[0]
        else:
            self._advance(state, 1)

    def _pass(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "drawn":
            raise GameError("You can only pass after drawing a playable card")
        log(state, f"{who(player)} passed")
        self._advance(state, 1)

    def _accept(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "challenge":
            raise GameError("There is no Wild Draw Four to respond to")
        self._draw(state, player, 4, rng)
        state["pending_wd4"] = None
        log(state, f"{who(player)} accepted and draws 4")
        self._advance(state, 1)

    def _challenge(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        pending = state["pending_wd4"]
        if state["phase"] != "challenge" or pending is None:
            raise GameError("There is no Wild Draw Four to challenge")
        state["pending_wd4"] = None
        if pending["guilty"]:
            self._draw(state, pending["by"], 4, rng)
            log(state, f"{who(player)} challenged successfully; {who(pending['by'])} draws 4")
            state["phase"] = "play"
        else:
            self._draw(state, player, 6, rng)
            log(state, f"{who(player)} challenged and failed; draws 6")
            self._advance(state, 1)

    def _declare(self, state: State, player: str) -> None:
        if len(state["hands"][player]) != 1 or player in state["uno_declared"]:
            raise GameError("You can only call UNO when you have one card left")
        self._mark_declared(state, player)

    @staticmethod
    def _mark_declared(state: State, player: str) -> None:
        if player not in state["uno_declared"]:
            state["uno_declared"].append(player)
        if state["uno_vulnerable"] == player:
            state["uno_vulnerable"] = None
        log(state, f"{who(player)} called UNO!")

    def _catch(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        target = action.get("target")
        if target == player:
            raise GameError("You cannot catch yourself")
        if target is None or target != state["uno_vulnerable"]:
            raise GameError("That player cannot be caught")
        state["uno_vulnerable"] = None
        self._draw(state, target, 2, rng)
        log(state, f"{who(player)} caught {who(target)} without UNO; {who(target)} draws 2")

    # -- leaving ---------------------------------------------------------------------

    def _remove_player(self, state: State, player: str) -> None:
        index = state["players"].index(player)
        was_current = index == state["current"]
        # Their cards go to the bottom of the draw pile (the deck's top is its end).
        state["deck"][:0] = state["hands"].pop(player)
        state["players"].remove(player)
        if player in state["uno_declared"]:
            state["uno_declared"].remove(player)
        if state["uno_vulnerable"] == player:
            state["uno_vulnerable"] = None
        pending = state["pending_wd4"]
        if pending and player in (pending["by"], pending["target"]):
            state["pending_wd4"] = None
            state["phase"] = "play"
        log(state, f"{who(player)} left the game")

        if len(state["players"]) == 1:
            state["winner"] = state["players"][0]
            state["win_reason"] = "Last player remaining"
            state["current"] = 0  # keep the index valid for views of the finished game
            return
        n = len(state["players"])
        if was_current:
            # The next player in the current direction takes the turn.
            state["current"] = (index if state["direction"] == 1 else index - 1) % n
            state["phase"] = "play"
            state["drawn_card"] = None
        elif index < state["current"]:
            state["current"] -= 1

    # -- queries ---------------------------------------------------------------------

    def awaiting(self, state: State) -> list[str]:
        return [] if state["winner"] else [self._current(state)]

    def outcome(self, state: State) -> Outcome | None:
        if state["winner"] is None:
            return None
        return Outcome(winners=[state["winner"]], reason=state["win_reason"])

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        current = self._current(state) if state["players"] else None
        top = state["discard"][-1]
        hand = state["hands"].get(player or "", [])
        my_turn = player == current and state["winner"] is None
        if my_turn and state["phase"] == "play":
            playable = [c for c in hand if is_playable(c, top, state["color"])]
        elif my_turn and state["phase"] == "drawn":
            playable = [state["drawn_card"]]
        else:
            playable = []
        pending = state["pending_wd4"]
        return {
            "players": [
                {"id": p, "cards": len(state["hands"][p]), "uno": p in state["uno_declared"]}
                for p in state["players"]
            ],
            "hand": [CARDS[c] for c in hand],
            "playable": playable,
            "top": CARDS[top],
            "color": state["color"],
            "direction": state["direction"],
            "current": current,
            "phase": state["phase"],
            "drawn_card": state["drawn_card"] if my_turn else None,
            "pending_wd4": None if pending is None else
            {"by": pending["by"], "target": pending["target"]},
            "catchable": state["uno_vulnerable"],
            "deck_count": len(state["deck"]),
            "discard_count": len(state["discard"]),
            "winner": state["winner"],
            "log": state["log"],
        }
