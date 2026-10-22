"""Snakes and Ladders rules (docs/games/snakes-and-ladders.md)."""

from __future__ import annotations

import random

import pytest

from app.games.snakes import FINISH, LADDERS, SNAKES, SnakesEngine
from tests.games.helpers import Dice, rejects

E = SnakesEngine()


def roll(state: dict, player: str, value: int) -> dict:
    return E.apply(state, player, {"type": "roll"}, Dice(value))


def at(positions: dict[str, int], current: int = 0) -> dict:
    state = E.new_game(list(positions), random.Random(1))
    state["positions"] = dict(positions)
    state["current"] = current
    return state


def test_start_off_board() -> None:
    state = E.new_game(["a", "b"], random.Random(1))
    assert state["positions"] == {"a": 0, "b": 0}
    assert E.awaiting(state) == ["a"]


def test_basic_move_and_turn_order() -> None:
    s = roll(at({"a": 0, "b": 0, "c": 0}), "a", 3)
    assert s["positions"]["a"] == 3 and E.awaiting(s) == ["b"]
    s = roll(s, "b", 2)
    s = roll(s, "c", 5)
    assert E.awaiting(s) == ["a"]
    assert s["last_roll"] == {"player": "c", "roll": 5, "from": 0, "landed": 5, "to": 5,
                              "jump": None}


def test_only_current_player_rolls_and_server_picks_die() -> None:
    state = at({"a": 0, "b": 0})
    rejects(E, state, "b", "not your turn", type="roll")
    rejects(E, state, "a", "Unknown action", type="move", to=100)
    # A client-supplied die value is ignored: the server rolls.
    s = E.apply(state, "a", {"type": "roll", "value": 6}, Dice(2))
    assert s["positions"]["a"] == 2


def test_six_gives_no_extra_turn() -> None:
    assert E.awaiting(roll(at({"a": 0, "b": 0}), "a", 6)) == ["b"]


@pytest.mark.parametrize(("bottom", "top"), sorted(LADDERS.items()))
def test_every_ladder_climbs(bottom: int, top: int) -> None:
    start = max(0, bottom - 6)
    s = roll(at({"a": start, "b": 0}), "a", bottom - start)
    assert s["positions"]["a"] == top and s["last_roll"]["jump"] == "ladder"


@pytest.mark.parametrize(("head", "tail"), sorted(SNAKES.items()))
def test_every_snake_bites(head: int, tail: int) -> None:
    s = roll(at({"a": head - 1, "b": 0}), "a", 1)
    assert s["positions"]["a"] == tail and s["last_roll"]["jump"] == "snake"


def test_exact_roll_needed_to_finish() -> None:
    s = roll(at({"a": 97, "b": 0}), "a", 4)  # would reach 101
    assert s["positions"]["a"] == 97 and E.awaiting(s) == ["b"] and E.outcome(s) is None
    s = roll(at({"a": 97, "b": 0}), "a", 3)
    assert s["positions"]["a"] == FINISH
    outcome = E.outcome(s)
    assert outcome is not None and outcome.winners == ["a"]
    rejects(E, s, "b", "game is over", type="roll")


def test_ladder_to_finish_wins() -> None:
    s = roll(at({"a": 77, "b": 0}), "a", 3)
    assert s["positions"]["a"] == FINISH and s["winner"] == "a"


def test_shared_squares_allowed() -> None:
    s = roll(at({"a": 0, "b": 3}), "a", 3)
    assert s["positions"] == {"a": 3, "b": 3}


def test_remove_player_keeps_turn_order() -> None:
    s = E.remove_player(at({"a": 5, "b": 6, "c": 7}, current=2), "a")
    assert E.awaiting(s) == ["c"]
    s = E.remove_player(s, "c")
    assert E.outcome(s).winners == ["b"]


def test_view_shows_board() -> None:
    view = E.view(at({"a": 5, "b": 6}), "b")
    assert view["positions"] == {"a": 5, "b": 6} and view["current"] == "a"
    assert view["ladders"][28] == 84 and view["snakes"][98] == 78


@pytest.mark.parametrize("seed", range(50))
def test_random_games_finish(seed: int) -> None:
    rng = random.Random(seed)
    state = E.new_game(["a", "b", "c"], rng)
    for _ in range(5000):
        if E.outcome(state):
            break
        state = E.apply(state, E.awaiting(state)[0], {"type": "roll"}, rng)
        assert all(0 <= p <= FINISH for p in state["positions"].values())
    assert E.outcome(state) is not None
