"""Admin accounts, admin sessions, and player (guest/host) sessions."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    ip_address: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class ScreenVisibility(enum.StrEnum):
    """Whether the host has hidden this guest's LanGamesHub interface (UI only)."""

    VISIBLE = "VISIBLE"
    HIDDEN = "HIDDEN"


class PlayerSession(Base):
    """A browser that asked to join. Its identity is the session, not the IP address."""

    __tablename__ = "player_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=16, create_constraint=True,
             name="session_status")
    )
    nickname: Mapped[str | None] = mapped_column(String(20))
    # The host's own player identity. Distinct from (and grants nothing of) admin auth.
    is_host: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Server-authoritative; only an admin can change it. Survives refresh, reconnect
    # and server restart. Never affects game state or authorization.
    screen_visibility: Mapped[ScreenVisibility] = mapped_column(
        Enum(ScreenVisibility, native_enum=False, length=8, create_constraint=True,
             name="screen_visibility"),
        default=ScreenVisibility.VISIBLE, server_default=ScreenVisibility.VISIBLE.value,
    )
    # Sound effects: whether the browser reports its sound as on (None = never reported),
    # and whether the host muted this guest. Presentation only, like screen visibility.
    sound_enabled: Mapped[bool | None] = mapped_column(Boolean)
    sound_muted_by_host: Mapped[bool] = mapped_column(Boolean, default=False,
                                                      server_default="false")


class AppSetting(Base):
    """Host-wide settings that must survive restarts (e.g. "mute every guest")."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB)
