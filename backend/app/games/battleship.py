"""Battleship engine. Rules: docs/games/battleship.md."""

from __future__ import annotations

import random
from typing import Any

from app.games.base import (
    Action,
    GameEngine,
    GameError,
    GameInfo,
    Outcome,
    State,
    log,
    require_int,
    who,
)

SIZE = 10
FLEET = {"carrier": 5, "battleship": 4, "cruiser": 3, "submarine": 3, "destroyer": 2}
SHIP_NAMES = {"carrier": "Carrier", "battleship": "Battleship", "cruiser": "Cruiser",
              "submarine": "Submarine", "destroyer": "Destroyer"}

Cell = tuple[int, int]


def ship_cells(row: int, col: int, orientation: str, length: int) -> list[Cell]:
    if orientation == "H":
        return [(row, col + i) for i in range(length)]
    return [(row + i, col) for i in range(length)]


def validate_fleet(ships: Any) -> list[dict[str, Any]]:
    """Turn a client placement into a fleet, or raise GameError."""
    if not isinstance(ships, list) or len(ships) != len(FLEET):
        raise GameError(f"Place exactly {len(FLEET)} ships")
    fleet: list[dict[str, Any]] = []
    occupied: set[Cell] = set()
    seen: set[str] = set()
    for ship in ships:
        if not isinstance(ship, dict) or not isinstance(ship.get("ship"), str) \
                or ship["ship"] not in FLEET:
            raise GameError("Unknown ship type")
        name = ship["ship"]
        if name in seen:
            raise GameError(f"{SHIP_NAMES[name]} placed twice")
        seen.add(name)
        row = require_int(ship, "row", 0, SIZE - 1)
        col = require_int(ship, "col", 0, SIZE - 1)
        orientation = ship.get("orientation")
        if orientation not in ("H", "V"):
            raise GameError("Orientation must be 'H' or 'V'")
        cells = ship_cells(row, col, orientation, FLEET[name])
        if any(not (0 <= r < SIZE and 0 <= c < SIZE) for r, c in cells):
            raise GameError(f"{SHIP_NAMES[name]} does not fit on the board there")
        if occupied & set(cells):
            raise GameError(f"{SHIP_NAMES[name]} overlaps another ship")
        occupied |= set(cells)
        fleet.append({"ship": name, "cells": [list(c) for c in cells]})
    return fleet


def random_fleet(rng: random.Random) -> list[dict[str, Any]]:
    while True:
        placement = []
        occupied: set[Cell] = set()
        for name, length in FLEET.items():
            for _ in range(200):
                orientation = rng.choice("HV")
                row = rng.randrange(SIZE if orientation == "H" else SIZE - length + 1)
                col = rng.randrange(SIZE - length + 1 if orientation == "H" else SIZE)
                cells = set(ship_cells(row, col, orientation, length))
                if not cells & occupied:
                    occupied |= cells
                    placement.append({"ship": name, "row": row, "col": col,
                                      "orientation": orientation})
                    break
        if len(placement) == len(FLEET):
            return validate_fleet(placement)


class BattleshipEngine(GameEngine):
    info = GameInfo("battleship", "Battleship", 2, 2,
                    "Hide your fleet and sink your opponent's ships first.")

    def new_game(self, players: list[str], rng: random.Random) -> State:
        return {
            "players": list(players),
            "fleets": {p: None for p in players},
            "shots": {p: [] for p in players},  # shots fired BY each player
            "phase": "placement",
            "current": 0,
            "winner": None,
            "win_reason": "",
            "log": [],
        }

    @staticmethod
    def _opponent(state: State, player: str) -> str:
        return next(p for p in state["players"] if p != player)

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        kind = action["type"]
        if kind in ("place", "place_random"):
            if state["phase"] != "placement":
                raise GameError("Ships are already placed")
            if state["fleets"][player] is not None:
                raise GameError("Your fleet is already placed")
            fleet = random_fleet(rng) if kind == "place_random" else validate_fleet(
                action.get("ships"))
            state["fleets"][player] = fleet
            log(state, f"{who(player)} placed their fleet")
            if all(f is not None for f in state["fleets"].values()):
                state["phase"] = "battle"
                log(state, f"All fleets placed. {who(state['players'][0])} fires first")
        elif kind == "fire":
            self._fire(state, player, action)
        else:
            raise GameError("Unknown action")

    def _fire(self, state: State, player: str, action: Action) -> None:
        if state["phase"] != "battle":
            raise GameError("Wait until both fleets are placed")
        if state["players"][state["current"]] != player:
            raise GameError("It is not your turn")
        row = require_int(action, "row", 0, SIZE - 1)
        col = require_int(action, "col", 0, SIZE - 1)
        if any(s["row"] == row and s["col"] == col for s in state["shots"][player]):
            raise GameError("You already fired at that square")
        opponent = self._opponent(state, player)
        fleet = state["fleets"][opponent]
        hit_ship = next((s for s in fleet if [row, col] in s["cells"]), None)
        shot: dict[str, Any] = {"row": row, "col": col, "result": "miss"}
        state["shots"][player].append(shot)
        coord = f"{'ABCDEFGHIJ'[row]}{col + 1}"
        if hit_ship is None:
            log(state, f"{who(player)} fired at {coord}: miss")
        else:
            hits = {(s["row"], s["col"]) for s in state["shots"][player] if s["result"] != "miss"}
            hits.add((row, col))
            if all(tuple(c) in hits for c in hit_ship["cells"]):
                shot["result"] = "sunk"
                shot["ship"] = hit_ship["ship"]
                log(state, f"{who(player)} fired at {coord}: sunk the "
                    f"{SHIP_NAMES[hit_ship['ship']]}")
            else:
                shot["result"] = "hit"
                log(state, f"{who(player)} fired at {coord}: hit")
            all_cells = {tuple(c) for s in fleet for c in s["cells"]}
            if all_cells <= hits:
                state["winner"] = player
                state["win_reason"] = "Sank the entire fleet"
                log(state, f"{who(player)} sank the entire fleet and wins")
                return
        state["current"] = 1 - state["current"]

    def _remove_player(self, state: State, player: str) -> None:
        state["winner"] = self._opponent(state, player)
        state["win_reason"] = "Opponent left"
        log(state, f"{who(player)} left the game")

    def awaiting(self, state: State) -> list[str]:
        if state["winner"]:
            return []
        if state["phase"] == "placement":
            return [p for p in state["players"] if state["fleets"][p] is None]
        return [state["players"][state["current"]]]

    def outcome(self, state: State) -> Outcome | None:
        if state["winner"] is None:
            return None
        return Outcome(winners=[state["winner"]], reason=state["win_reason"])

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        """Strictly filtered: the opponent's fleet layout never leaves the server."""
        base = {
            "phase": state["phase"],
            "players": state["players"],
            "current": state["players"][state["current"]] if state["phase"] == "battle" else None,
            "placed": {p: state["fleets"][p] is not None for p in state["players"]},
            "winner": state["winner"],
            "size": SIZE,
            "fleet_spec": FLEET,
            "log": state["log"],
        }
        if player not in state["players"]:
            return base
        opponent = self._opponent(state, player)
        sunk = [s["ship"] for s in state["shots"][player] if s["result"] == "sunk"]
        return {
            **base,
            "my_fleet": state["fleets"][player],
            "incoming": state["shots"][opponent],
            "my_shots": state["shots"][player],
            "enemy_sunk": sunk,
            "my_sunk": [s["ship"] for s in state["shots"][opponent] if s["result"] == "sunk"],
        }
