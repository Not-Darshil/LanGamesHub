"""UNO rules (docs/games/uno.md)."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from app.games.base import GameError
from app.games.uno import CARDS, UnoEngine, is_playable
from tests.games.helpers import StackedRandom, act, rejects

E = UnoEngine()
P = ["a", "b", "c"]


def card(color: str | None, kind: str, value: int | None = None, nth: int = 0) -> int:
    matches = [c["id"] for c in CARDS
               if c["color"] == color and c["kind"] == kind and c["value"] == value]
    return matches[nth]


def total_cards(state: dict) -> int:
    return sum(len(h) for h in state["hands"].values()) + len(state["deck"]) + len(state["discard"])


def setup(hands: dict[str, list[int]], top: int, color: str | None = None,
          players: list[str] | None = None, current: int = 0) -> dict:
    """A state with exact hands and top card; every other card is in the deck."""
    players = players or list(hands)
    state = E.new_game(players, random.Random(3))
    used = {c for h in hands.values() for c in h} | {top}
    state.update(
        hands={p: list(h) for p, h in hands.items()},
        discard=[top],
        deck=[c for c in range(108) if c not in used],
        color=color or CARDS[top]["color"],
        current=current, direction=1, phase="play", drawn_card=None, pending_wd4=None,
        uno_vulnerable=None, uno_declared=[], winner=None, log=[],
    )
    return state


R5, R7, G5, B2 = card("red", "number", 5), card("red", "number", 7), card("green", "number", 5), \
    card("blue", "number", 2)
Y9, Y1 = card("yellow", "number", 9), card("yellow", "number", 1)
R_SKIP, R_REV, R_D2 = card("red", "skip"), card("red", "reverse"), card("red", "draw2")
G_SKIP = card("green", "skip")
WILD, WD4 = card(None, "wild"), card(None, "wild4")


def test_deck_composition() -> None:
    kinds = Counter(c["kind"] for c in CARDS)
    assert len(CARDS) == 108
    assert kinds == {"number": 76, "skip": 8, "reverse": 8, "draw2": 8, "wild": 4, "wild4": 4}
    assert Counter(c["value"] for c in CARDS if c["kind"] == "number")[0] == 4


def test_deal_and_start_card() -> None:
    for seed in range(30):
        state = E.new_game(P, random.Random(seed))
        assert all(len(h) >= 7 for h in state["hands"].values())
        assert CARDS[state["discard"][-1]]["kind"] not in ("wild", "wild4")
        assert total_cards(state) == 108


def test_wild_start_card_is_replaced() -> None:
    state = E.new_game(P, StackedRandom([WD4, R5], skip=21))  # WD4 is turned first
    assert state["discard"] == [R5]
    assert WD4 in state["deck"]


@pytest.mark.parametrize(("start", "current", "direction", "seat0_cards"), [
    (R5, 0, 1, 7), (R_SKIP, 1, 1, 7), (R_REV, 2, -1, 7), (R_D2, 1, 1, 9)])
def test_starting_card_effects(start: int, current: int, direction: int,
                               seat0_cards: int) -> None:
    state = E.new_game(P, StackedRandom([start], skip=21))
    assert state["discard"] == [start]
    assert (state["current"], state["direction"]) == (current, direction)
    assert len(state["hands"]["a"]) == seat0_cards


def test_matching_rules() -> None:
    assert is_playable(R7, R5, "red")            # colour
    assert is_playable(G5, R5, "red")            # number
    assert not is_playable(B2, R5, "red")
    assert is_playable(G_SKIP, R_SKIP, "red")    # symbol
    assert not is_playable(G_SKIP, R5, "red")
    assert is_playable(WILD, R5, "red") and is_playable(WD4, R5, "red")
    assert is_playable(B2, WILD, "blue")         # chosen colour
    assert not is_playable(R5, WILD, "blue")


def test_play_validation() -> None:
    state = setup({"a": [R7, B2, WILD], "b": [Y9], "c": [Y1]}, top=R5)
    rejects(E, state, "b", "not your turn", type="play", card=Y9)
    rejects(E, state, "a", "not in your hand", type="play", card=Y9)
    rejects(E, state, "a", "not in your hand", type="play", card="7")
    rejects(E, state, "a", "cannot be played", type="play", card=B2)
    rejects(E, state, "a", "Choose a colour", type="play", card=WILD)
    rejects(E, state, "a", "Choose a colour", type="play", card=WILD, color="pink")
    rejects(E, state, "a", "Unknown action", type="teleport")
    after = act(E, state, "a", type="play", card=WILD, color="blue")
    assert after["color"] == "blue" and after["current"] == 1
    assert state["hands"]["a"] == [R7, B2, WILD]  # input state untouched


def test_skip_reverse_draw_two() -> None:
    hands = {"a": [R_SKIP, R_REV, R_D2, R7], "b": [Y9, Y1], "c": [Y1 + 1, B2]}
    s = act(E, setup(hands, top=R5), "a", type="play", card=R_SKIP)
    assert s["current"] == 2
    s = act(E, setup(hands, top=R5), "a", type="play", card=R_REV)
    assert (s["direction"], s["current"]) == (-1, 2)
    s = act(E, setup(hands, top=R5), "a", type="play", card=R_D2)
    assert s["current"] == 2 and len(s["hands"]["b"]) == 4


def test_reverse_with_two_players_acts_as_skip() -> None:
    s = act(E, setup({"a": [R_REV, R7], "b": [Y9]}, top=R5), "a", type="play", card=R_REV)
    assert s["current"] == 0 and s["direction"] == -1


def test_draw_playable_card_then_play_or_pass() -> None:
    state = setup({"a": [B2], "b": [Y9], "c": [Y1]}, top=R5)
    state["deck"].remove(R7)
    state["deck"].append(R7)  # next draw is playable
    s = act(E, state, "a", type="draw")
    assert (s["phase"], s["drawn_card"], s["current"]) == ("drawn", R7, 0)
    rejects(E, s, "a", "only play the card you drew", type="play", card=B2)
    rejects(E, s, "a", "cannot draw", type="draw")
    played = act(E, s, "a", type="play", card=R7)
    assert played["discard"][-1] == R7 and played["current"] == 1
    passed = act(E, s, "a", type="pass")
    assert passed["current"] == 1 and R7 in passed["hands"]["a"]


def test_draw_unplayable_card_ends_turn() -> None:
    state = setup({"a": [B2], "b": [Y9], "c": [Y1]}, top=R5)
    state["deck"].remove(Y9 + 1)
    state["deck"].append(Y9 + 1)  # yellow 9 (second copy): not playable on red 5
    s = act(E, state, "a", type="draw")
    assert s["current"] == 1 and s["phase"] == "play" and len(s["hands"]["a"]) == 2
    rejects(E, state, "a", "only pass after drawing", type="pass")


def test_reshuffle_when_deck_empty() -> None:
    state = setup({"a": [B2], "b": [Y9], "c": [Y1]}, top=R5)
    state["discard"] = state["deck"][:-1] + [R5]
    state["deck"] = state["deck"][-1:]
    s = act(E, state, "a", type="draw")
    s = act(E, s, s["players"][s["current"]], type="draw") if s["phase"] == "play" else s
    assert total_cards(s) == 108
    assert len(s["discard"]) >= 1 and s["discard"][-1] == R5


def wd4_state(guilty: bool) -> dict:
    hand = [WD4, R7 if guilty else B2, Y1]
    return setup({"a": hand, "b": [Y9, G5], "c": [B2 + 1]}, top=R5)


def test_wild_draw_four_accept() -> None:
    s = act(E, wd4_state(guilty=False), "a", type="play", card=WD4, color="green")
    assert (s["phase"], s["current"]) == ("challenge", 1)
    rejects(E, s, "b", "Respond to the Wild Draw Four", type="play", card=G5)
    rejects(E, s, "b", "cannot draw", type="draw")
    accepted = act(E, s, "b", type="accept")
    assert len(accepted["hands"]["b"]) == 6 and accepted["current"] == 2
    assert accepted["color"] == "green"


def test_wild_draw_four_challenge_guilty() -> None:
    s = act(E, wd4_state(guilty=True), "a", type="play", card=WD4, color="green")
    s = act(E, s, "b", type="challenge")
    assert len(s["hands"]["a"]) == 2 + 4
    assert len(s["hands"]["b"]) == 2 and s["current"] == 1 and s["phase"] == "play"
    assert s["color"] == "green"
    act(E, s, "b", type="play", card=G5)  # challenger takes a normal turn


def test_wild_draw_four_challenge_not_guilty() -> None:
    s = act(E, wd4_state(guilty=False), "a", type="play", card=WD4, color="green")
    s = act(E, s, "b", type="challenge")
    assert len(s["hands"]["b"]) == 2 + 6 and s["current"] == 2
    assert len(s["hands"]["a"]) == 2


def test_matching_number_of_other_colour_is_not_guilty() -> None:
    state = setup({"a": [WD4, G5, Y1], "b": [Y9], "c": [B2]}, top=R5)  # green 5 matches number
    s = act(E, state, "a", type="play", card=WD4, color="blue")
    s = act(E, s, "b", type="challenge")
    assert len(s["hands"]["b"]) == 7


def test_wd4_legality_is_hidden_from_views() -> None:
    s = act(E, wd4_state(guilty=True), "a", type="play", card=WD4, color="green")
    for p in P:
        view = E.view(s, p)
        assert view["pending_wd4"] == {"by": "a", "target": "b"}
        assert "guilty" not in str(view)


def test_uno_declared_with_play_is_safe() -> None:
    s = act(E, setup({"a": [R7, B2], "b": [Y9], "c": [Y1]}, top=R5), "a",
            type="play", card=R7, uno=True)
    assert s["uno_declared"] == ["a"] and s["uno_vulnerable"] is None
    rejects(E, s, "c", "cannot be caught", type="catch", target="a")
    assert E.view(s, "b")["players"][0]["uno"] is True


def test_missed_uno_can_be_caught_until_next_turn_action() -> None:
    s = act(E, setup({"a": [R7, B2], "b": [Y9, Y1], "c": [G5, B2 + 1]}, top=R5), "a",
            type="play", card=R7)
    assert s["uno_vulnerable"] == "a"
    rejects(E, s, "a", "cannot catch yourself", type="catch", target="a")
    rejects(E, s, "c", "cannot be caught", type="catch", target="b")
    caught = act(E, s, "c", type="catch", target="a")
    assert len(caught["hands"]["a"]) == 3 and caught["uno_vulnerable"] is None
    # If the next player acts first, the window closes.
    moved_on = act(E, s, "b", type="draw")
    rejects(E, moved_on, "c", "cannot be caught", type="catch", target="a")


def test_late_uno_call_protects() -> None:
    s = act(E, setup({"a": [R7, B2], "b": [Y9, G5], "c": [Y1]}, top=R5), "a",
            type="play", card=R7)
    s = act(E, s, "a", type="uno")
    assert s["uno_vulnerable"] is None
    rejects(E, s, "c", "cannot be caught", type="catch", target="a")
    rejects(E, s, "a", "one card left", type="uno")
    rejects(E, s, "b", "one card left", type="uno")


def test_last_card_wins_without_applying_effect() -> None:
    s = act(E, setup({"a": [R_D2], "b": [Y9], "c": [Y1]}, top=R5), "a", type="play", card=R_D2)
    assert s["winner"] == "a" and len(s["hands"]["b"]) == 1
    outcome = E.outcome(s)
    assert outcome is not None and outcome.winners == ["a"]
    rejects(E, s, "b", "game is over", type="draw")
    assert E.awaiting(s) == []


def test_remove_current_player_passes_turn_and_conserves_cards() -> None:
    state = setup({"a": [R7, B2], "b": [Y9], "c": [Y1]}, top=R5, current=1)
    s = E.remove_player(state, "b")
    assert s["players"] == ["a", "c"] and E._current(s) == "c"
    assert total_cards(s) == 108
    s = E.remove_player(s, "a")
    assert s["winner"] == "c" and E.outcome(s).reason == "Last player remaining"


def test_remove_wd4_target_cancels_penalty() -> None:
    s = act(E, wd4_state(guilty=False), "a", type="play", card=WD4, color="green")
    s = E.remove_player(s, "b")
    assert s["pending_wd4"] is None and s["phase"] == "play" and E._current(s) == "c"


def test_view_hides_other_hands_and_deck() -> None:
    state = setup({"a": [R7, B2], "b": [Y9], "c": [Y1]}, top=R5)
    view = E.view(state, "b")
    assert [c["id"] for c in view["hand"]] == [Y9]
    assert view["playable"] == []
    assert "deck" not in view and "hands" not in view
    assert view["players"][0] == {"id": "a", "cards": 2, "uno": False}
    assert E.view(state, "a")["playable"] == [R7]
    assert E.view(state, None)["hand"] == []


@pytest.mark.parametrize("seed", range(150))
def test_random_games_preserve_invariants(seed: int) -> None:
    """Fuzz: random legal (and some illegal) intents never corrupt the state."""
    rng = random.Random(seed)
    players = ["a", "b", "c", "d"][: rng.randint(2, 4)]
    state = E.new_game(players, rng)
    for _ in range(3000):
        if E.outcome(state) is not None:
            break
        current = E.awaiting(state)[0]
        view = E.view(state, current)
        if view["catchable"] and rng.random() < 0.5:
            catcher = rng.choice([p for p in state["players"] if p != view["catchable"]])
            state = E.apply(state, catcher, {"type": "catch", "target": view["catchable"]}, rng)
            continue
        if state["phase"] == "challenge":
            action = {"type": rng.choice(["accept", "challenge"])}
        elif view["playable"] and rng.random() < 0.85:
            action = {"type": "play", "card": rng.choice(view["playable"]),
                      "color": rng.choice(["red", "green", "blue", "yellow"]),
                      "uno": rng.random() < 0.7}
        elif state["phase"] == "drawn":
            action = {"type": "pass"}
        else:
            action = {"type": "draw"}
        if rng.random() < 0.05:  # random intents: legal ones apply, others must not corrupt
            bogus = {"type": "play", "card": rng.randrange(108), "color": "red"}
            before = state
            try:
                state = E.apply(state, rng.choice(state["players"]), bogus, rng)
            except GameError:
                assert state is before
            assert total_cards(state) == 108
            continue
        state = E.apply(state, current, action, rng)
        assert total_cards(state) == 108
        assert 0 <= state["current"] < len(state["players"])
    assert E.outcome(state) is not None, "game did not finish"
