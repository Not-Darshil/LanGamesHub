"""ORM models. Import every model module here so Alembic sees all tables."""

from app.db import Base
from app.models.auth import (
    AdminSession,
    AdminUser,
    AppSetting,
    PlayerSession,
    ScreenVisibility,
    SessionStatus,
)
from app.models.rooms import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    MatchResult,
    Room,
    RoomMember,
    RoomMessage,
    RoomStatus,
)

__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "AdminSession",
    "AdminUser",
    "AppSetting",
    "Base",
    "MatchResult",
    "PlayerSession",
    "Room",
    "RoomMember",
    "RoomMessage",
    "RoomStatus",
    "ScreenVisibility",
    "SessionStatus",
]
