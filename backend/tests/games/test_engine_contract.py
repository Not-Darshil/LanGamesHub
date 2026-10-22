"""Contract tests every registered engine must satisfy."""

from __future__ import annotations

import random

import pytest

from app.games.registry import GAMES


@pytest.mark.parametrize("game_type", sorted(GAMES))
@pytest.mark.parametrize("count", [2, 3, 4])
def test_views_work_after_players_leave(game_type: str, count: int) -> None:
    """Regression: the last remaining player sitting at a non-zero seat broke views."""
    engine = GAMES[game_type]
    if not engine.info.min_players <= count <= engine.info.max_players:
        pytest.skip("unsupported player count")
    players = [f"p{i}" for i in range(count)]
    state = engine.new_game(players, random.Random(4))
    if "current" in state:
        state["current"] = count - 1  # it is the last seat's turn
    for leaver in players[:-1]:
        state = engine.remove_player(state, leaver)
        for viewer in [*players, None]:
            engine.view(state, viewer)  # must not raise
        engine.awaiting(state)
    outcome = engine.outcome(state)
    assert outcome is not None and outcome.winners == [players[-1]]
