"""A tiny test-only engine for exercising rooms independently of real game rules.

Players take turns ("pass"); the current player may "claim" victory. Each player has
a secret number that only they may see, to verify hidden-information filtering.
"""

from __future__ import annotations

import random
from typing import Any

from app.games.base import Action, GameEngine, GameError, GameInfo, Outcome, State


class RelayEngine(GameEngine):
    info = GameInfo("relay", "Relay (test)", 2, 4, "Test-only game")

    def new_game(self, players: list[str], rng: random.Random) -> State:
        return {"players": list(players), "turn": 0, "winner": None,
                "secrets": {p: rng.randint(1, 10**9) for p in players}}

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["players"][state["turn"]] != player:
            raise GameError("Not your turn")
        if action["type"] == "pass":
            state["turn"] = (state["turn"] + 1) % len(state["players"])
        elif action["type"] == "claim":
            state["winner"] = player
        else:
            raise GameError("Unknown action")

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        return {"players": state["players"], "turn": state["players"][state["turn"]],
                "winner": state["winner"], "my_secret": state["secrets"].get(player or "")}

    def awaiting(self, state: State) -> list[str]:
        return [] if state["winner"] else [state["players"][state["turn"]]]

    def outcome(self, state: State) -> Outcome | None:
        return Outcome([state["winner"]], reason="claimed") if state["winner"] else None

    def _remove_player(self, state: State, player: str) -> None:
        index = state["players"].index(player)
        state["players"].remove(player)
        if index < state["turn"] or state["turn"] >= len(state["players"]):
            state["turn"] = max(0, state["turn"] - 1) % len(state["players"])
        if len(state["players"]) == 1:
            state["winner"] = state["players"][0]
