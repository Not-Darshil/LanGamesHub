"""Battleship rules and hidden-information guarantees (docs/games/battleship.md)."""

from __future__ import annotations

import json
import random

import pytest

from app.games.battleship import FLEET, SIZE, BattleshipEngine, random_fleet, validate_fleet
from tests.games.helpers import act, rejects

E = BattleshipEngine()

# Rows 0, 2, 4, 6, 8, all horizontal from column 0.
LAYOUT = [{"ship": name, "row": i * 2, "col": 0, "orientation": "H"}
          for i, name in enumerate(FLEET)]


def placed() -> dict:
    state = E.new_game(["a", "b"], random.Random(1))
    state = act(E, state, "a", type="place", ships=LAYOUT)
    return act(E, state, "b", type="place", ships=LAYOUT)


def fire(state: dict, player: str, row: int, col: int) -> dict:
    return act(E, state, player, type="fire", row=row, col=col)


def test_fleet_validation() -> None:
    assert len(validate_fleet(LAYOUT)) == 5
    bad = [
        (LAYOUT[:4], "exactly 5"),
        ([*LAYOUT[:4], {**LAYOUT[0]}], "placed twice"),
        ([{**LAYOUT[0], "ship": "yacht"}, *LAYOUT[1:]], "Unknown ship"),
        ([{**LAYOUT[0], "col": 6}, *LAYOUT[1:]], "does not fit"),
        ([{**LAYOUT[0], "row": 9, "orientation": "V"}, *LAYOUT[1:]], "does not fit"),
        ([{**LAYOUT[0], "row": 2}, *LAYOUT[1:]], "overlaps"),
        ([{**LAYOUT[0], "orientation": "D"}, *LAYOUT[1:]], "Orientation"),
        ([{**LAYOUT[0], "row": -1}, *LAYOUT[1:]], "integer"),
        ([{**LAYOUT[0], "row": "0"}, *LAYOUT[1:]], "integer"),
        ("ships", "exactly 5"),
        ([{**LAYOUT[0], "ship": ["carrier"]}, *LAYOUT[1:]], "Unknown ship"),
        ([{**LAYOUT[0], "ship": {"x": 1}}, *LAYOUT[1:]], "Unknown ship"),
    ]
    state = E.new_game(["a", "b"], random.Random(1))
    for ships, message in bad:
        rejects(E, state, "a", message, type="place", ships=ships)


def test_touching_ships_allowed() -> None:
    touching = [{"ship": n, "row": i, "col": 0, "orientation": "H"} for i, n in enumerate(FLEET)]
    assert len(validate_fleet(touching)) == 5


def test_random_fleets_are_valid() -> None:
    rng = random.Random(5)
    for _ in range(200):
        fleet = random_fleet(rng)
        cells = [tuple(c) for s in fleet for c in s["cells"]]
        assert len(cells) == len(set(cells)) == sum(FLEET.values())
        assert all(0 <= r < SIZE and 0 <= c < SIZE for r, c in cells)


def test_placement_phase_rules() -> None:
    state = E.new_game(["a", "b"], random.Random(1))
    assert E.awaiting(state) == ["a", "b"]
    rejects(E, state, "a", "Wait until both fleets", type="fire", row=0, col=0)
    state = act(E, state, "a", type="place_random")
    assert E.awaiting(state) == ["b"] and state["phase"] == "placement"
    rejects(E, state, "a", "already placed", type="place", ships=LAYOUT)
    assert E.view(state, "b")["placed"] == {"a": True, "b": False}
    state = act(E, state, "b", type="place", ships=LAYOUT)
    assert state["phase"] == "battle" and E.awaiting(state) == ["a"]
    rejects(E, state, "b", "already placed", type="place_random")


def test_fire_results_and_turns() -> None:
    state = placed()
    rejects(E, state, "b", "not your turn", type="fire", row=0, col=0)
    rejects(E, state, "a", "integer from 0 to 9", type="fire", row=10, col=0)
    s = fire(state, "a", 9, 9)
    assert s["shots"]["a"][-1]["result"] == "miss" and E.awaiting(s) == ["b"]
    s = fire(s, "b", 0, 0)
    assert s["shots"]["b"][-1]["result"] == "hit" and E.awaiting(s) == ["a"]  # no extra shot
    rejects(E, fire(s, "a", 5, 5), "b", "already fired", type="fire", row=0, col=0)


def test_sinking_and_victory() -> None:
    s = placed()
    # a sinks the destroyer (row 8, cols 0-1) while b keeps missing.
    misses = iter((r, c) for r in (1, 3, 5, 7, 9) for c in range(10))
    for col in range(2):
        s = fire(s, "a", 8, col)
        s = fire(s, "b", *next(misses))
    assert s["shots"]["a"][-1] == {"row": 8, "col": 1, "result": "sunk", "ship": "destroyer"}
    assert E.view(s, "a")["enemy_sunk"] == ["destroyer"]
    assert E.view(s, "b")["my_sunk"] == ["destroyer"]
    # Sink everything else.
    for row, name in zip((0, 2, 4, 6), FLEET, strict=False):
        for col in range(FLEET[name]):
            s = fire(s, "a", row, col)
            if E.outcome(s):
                break
            s = fire(s, "b", *next(misses))
    outcome = E.outcome(s)
    assert outcome is not None and outcome.winners == ["a"]
    rejects(E, s, "b", "game is over", type="fire", row=0, col=5)


def test_leaving_awards_opponent() -> None:
    s = E.remove_player(placed(), "b")
    assert E.outcome(s).winners == ["a"]


def _enemy_cells(state: dict, player: str) -> set[tuple[int, int]]:
    opponent = next(p for p in state["players"] if p != player)
    return {tuple(c) for s in state["fleets"][opponent] or [] for c in s["cells"]}


def _cells_in_view(view: dict) -> set[tuple[int, int]]:
    """Every coordinate pair that appears anywhere in a view."""
    found: set[tuple[int, int]] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("row"), int) and isinstance(node.get("col"), int):
                found.add((node["row"], node["col"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            if len(node) == 2 and all(isinstance(x, int) for x in node):
                found.add((node[0], node[1]))
            for v in node:
                walk(v)

    walk(view)
    return found


def test_views_never_reveal_unhit_enemy_ships() -> None:
    rng = random.Random(9)
    state = E.new_game(["a", "b"], rng)
    for p in ("a", "b"):
        assert "fleets" not in json.dumps(E.view(state, p))
        state = act(E, state, p, type="place_random", rng=rng)
    targets = {p: [(r, c) for r in range(SIZE) for c in range(SIZE)] for p in ("a", "b")}
    for t in targets.values():
        rng.shuffle(t)
    while not E.outcome(state):
        for p in ("a", "b"):
            view = E.view(state, p)
            hit = {(s["row"], s["col"]) for s in view["my_shots"] if s["result"] != "miss"}
            own = {tuple(c) for s in view["my_fleet"] for c in s["cells"]}
            visible = _cells_in_view(view) - own - {(s["row"], s["col"]) for s in view["incoming"]}
            assert not (visible & _enemy_cells(state, p)) - hit
        player = E.awaiting(state)[0]
        state = fire(state, player, *targets[player].pop())
    # Still hidden after the game ends.
    loser = next(p for p in state["players"] if p != state["winner"])
    view = E.view(state, loser)
    hit = {(s["row"], s["col"]) for s in view["my_shots"] if s["result"] != "miss"}
    own = {tuple(c) for s in view["my_fleet"] for c in s["cells"]}
    leaked = (_cells_in_view(view) - own - {(s["row"], s["col"]) for s in view["incoming"]})
    assert not (leaked & _enemy_cells(state, loser)) - hit


def test_spectator_view_has_no_fleets() -> None:
    view = E.view(placed(), None)
    assert "my_fleet" not in view and "fleets" not in view


@pytest.mark.parametrize("seed", range(20))
def test_random_games_finish(seed: int) -> None:
    rng = random.Random(seed)
    state = E.new_game(["a", "b"], rng)
    for p in ("a", "b"):
        state = act(E, state, p, type="place_random", rng=rng)
    cells = {p: [(r, c) for r in range(SIZE) for c in range(SIZE)] for p in ("a", "b")}
    for p in cells:
        rng.shuffle(cells[p])
    while not E.outcome(state):
        p = E.awaiting(state)[0]
        state = fire(state, p, *cells[p].pop())
    assert E.outcome(state) is not None
