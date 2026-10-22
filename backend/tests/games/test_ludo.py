"""Ludo rules (docs/games/ludo.md)."""

from __future__ import annotations

import random

import pytest

from app.games.ludo import HOME, SAFE_SQUARES, YARD, LudoEngine, square
from tests.games.helpers import Dice, rejects

E = LudoEngine()


def game(tokens: dict[str, list[int]], current: int = 0) -> dict:
    state = E.new_game(list(tokens), random.Random(1))
    state["tokens"] = {p: list(t) for p, t in tokens.items()}
    state["current"] = current
    return state


def roll(state: dict, player: str, value: int) -> dict:
    return E.apply(state, player, {"type": "roll"}, Dice(value))


def move(state: dict, player: str, token: int) -> dict:
    return E.apply(state, player, {"type": "move", "token": token}, random.Random(1))


Y = [YARD] * 4


@pytest.mark.parametrize(("count", "colors"), [
    (2, ["red", "yellow"]), (3, ["red", "green", "yellow"]),
    (4, ["red", "green", "yellow", "blue"])])
def test_colour_assignment(count: int, colors: list[str]) -> None:
    players = [f"p{i}" for i in range(count)]
    state = E.new_game(players, random.Random(1))
    assert [state["colors"][p] for p in players] == colors
    assert all(t == Y for t in state["tokens"].values())


def test_square_mapping() -> None:
    assert square("red", 0) == 0 and square("green", 0) == 13
    assert square("blue", 13) == 0 and square("yellow", 50) == 24
    assert square("red", 51) is None and square("red", YARD) is None


def test_need_six_to_leave_yard() -> None:
    s = roll(game({"a": Y, "b": Y}), "a", 5)
    assert s["phase"] == "roll" and E.awaiting(s) == ["b"]
    s = roll(game({"a": Y, "b": Y}), "a", 6)
    assert s["phase"] == "move" and E.view(s, "a")["legal_tokens"] == [0, 1, 2, 3]
    s = move(s, "a", 2)
    assert s["tokens"]["a"] == [YARD, YARD, 0, YARD]
    assert E.awaiting(s) == ["a"] and s["phase"] == "roll"  # six: roll again


def test_turn_and_phase_enforcement() -> None:
    state = game({"a": [0, YARD, YARD, YARD], "b": Y})
    rejects(E, state, "b", "not your turn", type="roll")
    rejects(E, state, "a", "Roll the die first", type="move", token=0)
    s = roll(state, "a", 3)
    rejects(E, s, "a", "Move a token first", type="roll")
    rejects(E, s, "a", "cannot move with this roll", type="move", token=1)
    rejects(E, s, "a", "must be an integer", type="move", token=7)
    rejects(E, s, "a", "must be an integer", type="move", token="0")
    s = move(s, "a", 0)
    assert s["tokens"]["a"][0] == 3 and E.awaiting(s) == ["b"]


def test_exact_roll_to_reach_home() -> None:
    s = roll(game({"a": [53, YARD, YARD, YARD], "b": Y}), "a", 4)  # 57 > 56
    assert s["phase"] == "roll" and E.awaiting(s) == ["b"]
    s = roll(game({"a": [53, YARD, YARD, YARD], "b": Y}), "a", 3)
    s = move(s, "a", 0)
    assert s["tokens"]["a"][0] == HOME
    # Home tokens never move again.
    s = roll(game({"a": [HOME, 10, YARD, YARD], "b": Y}), "a", 2)
    assert E.view(s, "a")["legal_tokens"] == [1]


def test_capture_sends_opponent_home() -> None:
    # Two players: b is yellow (start 26). Yellow progress 30 is absolute square 4.
    s = roll(game({"a": [1, YARD, YARD, YARD], "b": [30, 2, YARD, YARD]}), "a", 3)
    s = move(s, "a", 0)
    assert square("red", s["tokens"]["a"][0]) == 4
    assert s["tokens"]["b"] == [YARD, 2, YARD, YARD]


def test_capture_all_tokens_on_square() -> None:
    s = roll(game({"a": [1, YARD, YARD, YARD], "b": [30, 30, YARD, YARD]}), "a", 3)
    s = move(s, "a", 0)
    assert s["tokens"]["b"] == [YARD, YARD, YARD, YARD]


@pytest.mark.parametrize("safe", sorted(SAFE_SQUARES))
def test_no_capture_on_safe_squares(safe: int) -> None:
    """Contrast: test_capture_sends_opponent_home shows the same move captures elsewhere."""
    # Yellow token sits on the safe absolute square; red lands on it.
    yellow_progress = (safe - 26) % 52
    red_target = safe  # red progress == absolute square
    if red_target == 0:
        return  # red's own start: red cannot "move onto" it except by leaving the yard
    start = red_target - 2
    assert square("yellow", yellow_progress) == safe
    s = roll(game({"a": [start, YARD, YARD, YARD], "b": [yellow_progress, YARD, YARD, YARD]}),
             "a", 2)
    s = move(s, "a", 0)
    assert square("red", s["tokens"]["a"][0]) == safe
    assert s["tokens"]["b"][0] == yellow_progress


def test_leaving_yard_onto_occupied_start_is_safe() -> None:
    # Yellow token on red's start square (abs 0 = yellow progress 26) survives.
    s = roll(game({"a": Y, "b": [26, YARD, YARD, YARD]}), "a", 6)
    s = move(s, "a", 0)
    assert s["tokens"]["b"][0] == 26 and s["tokens"]["a"][0] == 0


def test_own_tokens_stack_and_home_column_is_private() -> None:
    s = roll(game({"a": [3, 5, YARD, YARD], "b": Y}), "a", 2)
    s = move(s, "a", 0)
    assert s["tokens"]["a"][:2] == [5, 5]
    # Red in its home column is never captured by anything.
    s = roll(game({"a": [52, YARD, YARD, YARD], "b": [36, YARD, YARD, YARD]}, current=1), "b", 3)
    s = move(s, "b", 0)
    assert s["tokens"]["a"][0] == 52


def test_three_sixes_forfeit_turn() -> None:
    s = roll(game({"a": [0, YARD, YARD, YARD], "b": Y}), "a", 6)
    s = move(s, "a", 0)
    s = roll(s, "a", 6)
    s = move(s, "a", 0)
    s = roll(s, "a", 6)
    assert E.awaiting(s) == ["b"] and s["sixes"] == 0
    assert s["tokens"]["a"][0] == 12


def test_six_with_no_move_rolls_again() -> None:
    s = roll(game({"a": [HOME, HOME, HOME, 53], "b": Y}), "a", 6)
    assert E.awaiting(s) == ["a"] and s["phase"] == "roll" and s["sixes"] == 1


def test_win_with_all_tokens_home() -> None:
    s = roll(game({"a": [HOME, HOME, HOME, 54], "b": Y}), "a", 2)
    s = move(s, "a", 3)
    assert E.outcome(s).winners == ["a"]
    rejects(E, s, "b", "game is over", type="roll")


def test_remove_player() -> None:
    s = E.remove_player(game({"a": Y, "b": Y, "c": Y}, current=1), "b")
    assert E.awaiting(s) == ["c"] and "b" not in s["tokens"]
    s = E.remove_player(s, "a")
    assert E.outcome(s).winners == ["c"]


@pytest.mark.parametrize("seed", range(60))
def test_random_games_finish(seed: int) -> None:
    rng = random.Random(seed)
    players = ["a", "b", "c", "d"][: rng.randint(2, 4)]
    state = E.new_game(players, rng)
    for _ in range(20000):
        if E.outcome(state):
            break
        current = E.awaiting(state)[0]
        view = E.view(state, current)
        if state["phase"] == "roll":
            state = E.apply(state, current, {"type": "roll"}, rng)
        else:
            token = rng.choice(view["legal_tokens"])
            state = E.apply(state, current, {"type": "move", "token": token}, rng)
        for tokens in state["tokens"].values():
            assert all(YARD <= t <= HOME for t in tokens)
    assert E.outcome(state) is not None
