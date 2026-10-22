"""Per-application runtime context: settings, database, realtime hub, rate limiters."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.ratelimit import RateLimiter
from app.realtime.hub import Hub

T = TypeVar("T")


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    hub: Hub = field(init=False)
    access_limiter: RateLimiter = field(init=False)
    login_limiter: RateLimiter = field(init=False)
    action_limiter: RateLimiter = field(init=False)
    chat_limiter: RateLimiter = field(init=False)
    reaction_limiter: RateLimiter = field(init=False)
    # Dice and shuffles use the OS CSPRNG so outcomes cannot be predicted by clients.
    rng: random.Random = field(default_factory=random.SystemRandom)

    def __post_init__(self) -> None:
        self.access_limiter = RateLimiter(self.settings.rate_limit_access_per_minute, 60)
        self.login_limiter = RateLimiter(self.settings.rate_limit_login_per_minute, 60)
        self.action_limiter = RateLimiter(self.settings.rate_limit_actions_per_second, 1)
        # Chat is social, not gameplay: a few lines and reactions per few seconds is plenty.
        self.chat_limiter = RateLimiter(5, 10)
        self.reaction_limiter = RateLimiter(8, 5)

    def transaction(self, fn: Callable[[Session], T]) -> T:
        """Run ``fn`` in one committed transaction (rolled back on error)."""
        with self.sessions.begin() as db:
            return fn(db)

    async def run(self, fn: Callable[[Session], T]) -> T:
        return await run_in_threadpool(self.transaction, fn)
