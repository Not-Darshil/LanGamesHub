from __future__ import annotations

import random
from typing import Any

from app.games.base import GameEngine, GameError, State


class StackedRandom(random.Random):
    """A seeded RNG whose first shuffle stacks the deck (drawn from the end).

    After ``skip`` cards are dealt, the next cards drawn are ``flips`` in order.
    """

    def __init__(self, flips: list[int], skip: int, seed: int = 7) -> None:
        super().__init__(seed)
        self._flips = list(flips)
        self._skip = skip

    def shuffle(self, x: list[Any]) -> None:  # type: ignore[override]
        super().shuffle(x)
        if self._flips:
            rest = [c for c in x if c not in self._flips]
            cut = len(rest) - self._skip
            x[:] = rest[:cut] + list(reversed(self._flips)) + rest[cut:]
            self._flips = []


def act(engine: GameEngine, state: State, player: str, rng: random.Random | None = None,
        **action: Any) -> State:
    return engine.apply(state, player, action, rng or random.Random(1))


def rejects(engine: GameEngine, state: State, player: str, message: str = "",
            **action: Any) -> None:
    import pytest

    with pytest.raises(GameError, match=message):
        engine.apply(state, player, action, random.Random(1))


class Dice(random.Random):
    """An RNG whose randint returns scripted values (for dice), then falls back to seeded."""

    def __init__(self, *rolls: int, seed: int = 11) -> None:
        super().__init__(seed)
        self.rolls = list(rolls)

    def randint(self, a: int, b: int) -> int:  # type: ignore[override]
        if self.rolls:
            value = self.rolls.pop(0)
            assert a <= value <= b
            return value
        return super().randint(a, b)
