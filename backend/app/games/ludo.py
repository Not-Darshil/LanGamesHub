"""Ludo engine. Rules: docs/games/ludo.md."""

from __future__ import annotations

import random
from typing import Any

from app.games.base import (
    Action,
    GameEngine,
    GameError,
    GameInfo,
    Outcome,
    Placing,
    State,
    log,
    rank,
    require_int,
    who,
)


TRACK = 52
LAST_TRACK = 50   # last main-track progress before the home column
HOME = 56
YARD = -1
TOKENS = 4
START = {"red": 0, "green": 13, "yellow": 26, "blue": 39}
SAFE_SQUARES = frozenset({0, 13, 26, 39, 8, 21, 34, 47})
COLORS_BY_COUNT = {2: ["red", "yellow"], 3: ["red", "green", "yellow"],
                   4: ["red", "green", "yellow", "blue"]}


def square(color: str, progress: int) -> int | None:
    """Absolute main-track square for a token, or None if not on the main track."""
    if 0 <= progress <= LAST_TRACK:
        return (START[color] + progress) % TRACK
    return None


class LudoEngine(GameEngine):
    info = GameInfo("ludo", "Ludo", 2, 4,
                    "Roll a six to leave the yard and race all four tokens home.")

    def new_game(self, players: list[str], rng: random.Random) -> State:
        colors = COLORS_BY_COUNT[len(players)]
        return {
            "players": list(players),
            "colors": dict(zip(players, colors, strict=True)),
            "tokens": {p: [YARD] * TOKENS for p in players},
            "current": 0,
            "phase": "roll",
            "roll": None,
            "sixes": 0,
            "winner": None,
            "win_reason": "",
            "log": [],
        }

    # -- rules -----------------------------------------------------------------------

    @staticmethod
    def legal_tokens(state: State, player: str, roll: int) -> list[int]:
        legal = []
        for i, progress in enumerate(state["tokens"][player]):
            if progress == YARD:
                if roll == 6:
                    legal.append(i)
            elif progress < HOME and progress + roll <= HOME:
                legal.append(i)
        return legal

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["players"][state["current"]] != player:
            raise GameError("It is not your turn")
        if action["type"] == "roll":
            self._roll(state, player, rng)
        elif action["type"] == "move":
            self._move(state, player, action)
        else:
            raise GameError("Unknown action")

    def _roll(self, state: State, player: str, rng: random.Random) -> None:
        if state["phase"] != "roll":
            raise GameError("Move a token first")
        roll = rng.randint(1, 6)
        state["roll"] = roll
        state["sixes"] = state["sixes"] + 1 if roll == 6 else 0
        if state["sixes"] == 3:
            log(state, f"{who(player)} rolled a third 6 in a row and loses the turn")
            self._end_turn(state)
            return
        legal = self.legal_tokens(state, player, roll)
        if legal:
            state["phase"] = "move"
            log(state, f"{who(player)} rolled {roll}")
        elif roll == 6:
            log(state, f"{who(player)} rolled 6 but cannot move; rolls again")
        else:
            log(state, f"{who(player)} rolled {roll} and cannot move")
            self._end_turn(state)

    def _move(self, state: State, player: str, action: Action) -> None:
        if state["phase"] != "move":
            raise GameError("Roll the die first")
        token = require_int(action, "token", 0, TOKENS - 1)
        roll = state["roll"]
        if token not in self.legal_tokens(state, player, roll):
            raise GameError("That token cannot move with this roll")
        color = state["colors"][player]
        tokens = state["tokens"][player]
        before = tokens[token]
        tokens[token] = 0 if before == YARD else before + roll
        after = tokens[token]

        where = square(color, after)
        if before == YARD:
            message = f"{who(player)} brought a token out"
        elif after == HOME:
            message = f"{who(player)} moved a token home"
        else:
            message = f"{who(player)} moved a token {roll}"
        captured = []
        if where is not None and where not in SAFE_SQUARES:
            for other in state["players"]:
                if other == player:
                    continue
                other_color = state["colors"][other]
                for i, p in enumerate(state["tokens"][other]):
                    if square(other_color, p) == where:
                        state["tokens"][other][i] = YARD
                        captured.append(other)
        if captured:
            message += " and captured " + ", ".join(who(o) for o in dict.fromkeys(captured))
        log(state, message)

        if all(p == HOME for p in tokens):
            state["winner"] = player
            state["win_reason"] = "All four tokens home"
            log(state, f"{who(player)} brought all tokens home and wins")
            return
        state["phase"] = "roll"
        if roll == 6:
            log(state, f"{who(player)} rolls again")
        else:
            self._end_turn(state)

    @staticmethod
    def _end_turn(state: State) -> None:
        state["current"] = (state["current"] + 1) % len(state["players"])
        state["phase"] = "roll"
        state["sixes"] = 0

    def _remove_player(self, state: State, player: str) -> None:
        index = state["players"].index(player)
        was_current = index == state["current"]
        state["players"].remove(player)
        del state["tokens"][player]
        log(state, f"{who(player)} left the game")
        if len(state["players"]) == 1:
            state["winner"] = state["players"][0]
            state["win_reason"] = "Last player remaining"
            state["current"] = 0  # keep the index valid for views of the finished game
            return
        if index < state["current"]:
            state["current"] -= 1
        state["current"] %= len(state["players"])
        if was_current:
            state["phase"] = "roll"
            state["sixes"] = 0
            state["roll"] = None

    # -- queries ---------------------------------------------------------------------

    def awaiting(self, state: State) -> list[str]:
        return [] if state["winner"] else [state["players"][state["current"]]]

    def outcome(self, state: State) -> Outcome | None:
        if state["winner"] is None:
            return None
        return Outcome(winners=[state["winner"]], reason=state["win_reason"])

    def standings(self, state: State) -> list[Placing]:
        """Winner first, then by tokens home, then by total distance travelled."""
        def key(p: str) -> tuple[bool, int, int]:
            tokens = state["tokens"][p]
            return (p == state["winner"], sum(t == HOME for t in tokens),
                    sum(max(t, 0) for t in tokens))
        return rank([(p, key(p), "Winner" if p == state["winner"]
                      else f"{key(p)[1]}/{TOKENS} home") for p in state["players"]])

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        current = state["players"][state["current"]] if state["players"] else None
        legal = (self.legal_tokens(state, current, state["roll"])
                 if current and state["phase"] == "move" and not state["winner"] else [])
        return {
            "players": [{"id": p, "color": state["colors"][p]} for p in state["players"]],
            "tokens": state["tokens"],
            "current": current,
            "phase": state["phase"],
            "roll": state["roll"],
            "sixes": state["sixes"],
            "legal_tokens": legal,
            "winner": state["winner"],
            "start": START,
            "safe_squares": sorted(SAFE_SQUARES),
            "log": state["log"],
        }
