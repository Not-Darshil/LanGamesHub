"""Shared interface every game engine implements.

Engines are pure and server-authoritative: they take the current JSON-serializable
state plus one player's requested action, validate it against the rules, and return
a new state. Clients only ever send intents ("play card 17"); dice, shuffles and
outcomes are decided here with the server's RNG. ``view`` is the only way state
leaves the server, and it must strip anything the given player may not see.

Player ids are opaque strings (the room member's session id).
"""

from __future__ import annotations

import copy
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.services.errors import ServiceError

State = dict[str, Any]
Action = dict[str, Any]
Options = dict[str, Any]


class GameError(ServiceError):
    """An illegal or malformed action. The state is left unchanged."""

    status_code = 400


@dataclass(frozen=True)
class GameInfo:
    game_type: str
    name: str
    min_players: int
    max_players: int
    description: str


@dataclass(frozen=True)
class Outcome:
    winners: list[str]
    draw: bool = False
    reason: str = ""


@dataclass(frozen=True)
class Placing:
    player: str
    place: int        # 1 = first; tied players share a place ("1, 2, 2, 4")
    detail: str = ""  # e.g. "3 cards left"


def rank(entries: list[tuple[str, tuple[Any, ...], str]]) -> list[Placing]:
    """Competition ranking of (player, key, detail) entries; a higher key is better."""
    ordered = sorted(entries, key=lambda e: e[1], reverse=True)
    placings: list[Placing] = []
    for i, (player, key, detail) in enumerate(ordered):
        tied = i > 0 and ordered[i - 1][1] == key
        placings.append(Placing(player, placings[-1].place if tied else i + 1, detail))
    return placings


class GameEngine(ABC):
    info: GameInfo
    # True when ``deadline`` can return a time: the server then checks these games for
    # expired clocks even when nobody acts (see rooms.expire_clocks).
    timed: bool = False

    @abstractmethod
    def new_game(self, players: list[str], rng: random.Random) -> State:
        """Initial state for ``players`` in seat order."""

    @abstractmethod
    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        """Validate and apply ``action`` to ``state`` in place, or raise GameError."""

    @abstractmethod
    def view(self, state: State, player: str | None) -> dict[str, Any]:
        """What ``player`` may see (None = a non-participant). Never leaks hidden info."""

    @abstractmethod
    def awaiting(self, state: State) -> list[str]:
        """Players the game is waiting on (usually the one whose turn it is)."""

    @abstractmethod
    def outcome(self, state: State) -> Outcome | None:
        """The result once the game is over, else None."""

    @abstractmethod
    def _remove_player(self, state: State, player: str) -> None:
        """Remove a player who left or was revoked, in place. May end the game."""

    def standings(self, state: State) -> list[Placing]:
        """Order of the players still in the game, best first. Called when it ends.

        The default puts the winners first and everyone else level; games with progress
        (cards left, squares, tokens home) rank the rest by how close they came.
        """
        outcome = self.outcome(state)
        winners = set(outcome.winners) if outcome else set()
        return rank([(p, (p in winners,), "Winner" if p in winners else "")
                     for p in state["players"]])

    # -- optional hooks: per-room options and clocks ----------------------------------

    def validate_options(self, options: Options | None) -> Options:
        """Normalize the room options chosen at creation, or raise GameError."""
        if options:
            raise GameError(f"{self.info.name} has no options")
        return {}

    def options_label(self, options: Options) -> str | None:
        """A short human-readable summary of the options (shown on room cards)."""
        return None

    def configure(self, state: State, options: Options) -> None:
        """Apply validated room options to a freshly created state, in place."""

    def now(self) -> float:
        """Wall-clock seconds as this engine sees them (engines with clocks inject this)."""
        return time.time()

    def deadline(self, state: State) -> float | None:
        """Epoch seconds at which the game ends on time unless someone acts first."""
        return None

    def expire(self, state: State) -> State:
        """Apply any clock that has run out. Returns ``state`` itself when nothing changed."""
        return state

    def start(self, players: list[str], rng: random.Random, options: Options | None = None) -> State:
        state = self.new_game(players, rng)
        self.configure(state, options or {})
        return state

    # -- template methods: copy first so a failed action never corrupts state --------

    def apply(self, state: State, player: str, action: Action, rng: random.Random) -> State:
        if self.outcome(state) is not None:
            raise GameError("The game is over")
        if player not in state["players"]:
            raise GameError("You are not playing in this game")
        if not isinstance(action, dict) or not isinstance(action.get("type"), str):
            raise GameError("Malformed action")
        new_state = copy.deepcopy(state)
        self._apply(new_state, player, action, rng)
        return new_state

    def remove_player(self, state: State, player: str) -> State:
        if player not in state["players"] or self.outcome(state) is not None:
            return state
        new_state = copy.deepcopy(state)
        self._remove_player(new_state, player)
        return new_state


def require_int(action: Action, key: str, low: int, high: int) -> int:
    value = action.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise GameError(f"'{key}' must be an integer from {low} to {high}")
    return value


def who(player: str) -> str:
    """Reference a player inside a log message; clients substitute the nickname."""
    return "{{" + player + "}}"


def log(state: State, message: str, limit: int = 30) -> None:
    """Append a public, human-readable event to the game log (players via ``who``)."""
    entries = state.setdefault("log", [])
    entries.append(message)
    del entries[:-limit]
