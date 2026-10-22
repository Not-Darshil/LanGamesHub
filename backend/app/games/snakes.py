"""Snakes and Ladders engine. Rules: docs/games/snakes-and-ladders.md."""

from __future__ import annotations

import random
from typing import Any

from app.games.base import Action, GameEngine, GameError, GameInfo, Outcome, State, log, who

FINISH = 100
LADDERS = {1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100}
SNAKES = {16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78}
JUMPS = {**LADDERS, **SNAKES}
assert not set(JUMPS) & set(JUMPS.values()), "jumps must not chain"


class SnakesEngine(GameEngine):
    info = GameInfo("snakes", "Snakes and Ladders", 2, 4,
                    "Race to square 100. Climb ladders, avoid snakes.")

    def new_game(self, players: list[str], rng: random.Random) -> State:
        return {
            "players": list(players),
            "positions": {p: 0 for p in players},
            "current": 0,
            "last_roll": None,
            "winner": None,
            "win_reason": "",
            "log": [],
        }

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if action["type"] != "roll":
            raise GameError("Unknown action")
        if state["players"][state["current"]] != player:
            raise GameError("It is not your turn")
        roll = rng.randint(1, 6)
        start = state["positions"][player]
        target = start + roll
        jump = None
        if target > FINISH:
            end = start
            log(state, f"{who(player)} rolled {roll} but needs exactly {FINISH - start}")
        else:
            end = JUMPS.get(target, target)
            if target in LADDERS:
                jump = "ladder"
            elif target in SNAKES:
                jump = "snake"
            log(state, f"{who(player)} rolled {roll}: {start} → {target}"
                + (f", climbed a ladder to {end}" if jump == "ladder" else "")
                + (f", bitten by a snake down to {end}" if jump == "snake" else ""))
        state["positions"][player] = end
        state["last_roll"] = {"player": player, "roll": roll, "from": start, "landed": target,
                              "to": end, "jump": jump}
        if end == FINISH:
            state["winner"] = player
            state["win_reason"] = f"Reached square {FINISH}"
            log(state, f"{who(player)} reached {FINISH} and wins")
            return
        state["current"] = (state["current"] + 1) % len(state["players"])

    def _remove_player(self, state: State, player: str) -> None:
        index = state["players"].index(player)
        state["players"].remove(player)
        del state["positions"][player]
        log(state, f"{who(player)} left the game")
        if len(state["players"]) == 1:
            state["winner"] = state["players"][0]
            state["win_reason"] = "Last player remaining"
            state["current"] = 0  # keep the index valid for views of the finished game
            return
        if index < state["current"]:
            state["current"] -= 1
        state["current"] %= len(state["players"])

    def awaiting(self, state: State) -> list[str]:
        return [] if state["winner"] else [state["players"][state["current"]]]

    def outcome(self, state: State) -> Outcome | None:
        if state["winner"] is None:
            return None
        return Outcome(winners=[state["winner"]], reason=state["win_reason"])

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        return {
            "players": state["players"],
            "positions": state["positions"],
            "current": state["players"][state["current"]] if state["players"] else None,
            "last_roll": state["last_roll"],
            "winner": state["winner"],
            "ladders": LADDERS,
            "snakes": SNAKES,
            "log": state["log"],
        }
