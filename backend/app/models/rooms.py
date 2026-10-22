"""Game rooms, their members, and recorded match results."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RoomStatus(enum.StrEnum):
    CREATED = "CREATED"                          # proposed by a player, awaiting host approval
    WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"  # approved; open for joining
    READY_TO_START = "READY_TO_START"            # enough players, all ready; host may start
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


ACTIVE_STATUSES = (RoomStatus.CREATED, RoomStatus.WAITING_FOR_PLAYERS,
                   RoomStatus.READY_TO_START, RoomStatus.IN_PROGRESS)
TERMINAL_STATUSES = (RoomStatus.COMPLETED, RoomStatus.CANCELLED)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    game_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, native_enum=False, length=24, create_constraint=True, name="room_status")
    )
    max_players: Mapped[int] = mapped_column(Integer)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_admin: Mapped[bool] = mapped_column(Boolean)
    creator_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_sessions.id", ondelete="SET NULL"))
    creator_label: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Seated players at start: [{"id", "session_id", "nickname", "seat"}]. Kept so the
    # game can still name players who leave mid-match.
    participants: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    status_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    members: Mapped[list[RoomMember]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="RoomMember.seat")


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "session_id"),
        UniqueConstraint("room_id", "seat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("player_sessions.id", ondelete="CASCADE"), index=True)
    seat: Mapped[int] = mapped_column(Integer)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    room: Mapped[Room] = relationship(back_populates="members")


class MatchResult(Base):
    """Durable record of how a started match ended; survives room removal."""

    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    room_name: Mapped[str] = mapped_column(String(40))
    game_type: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))  # WIN, DRAW, ABORTED, CANCELLED
    winners: Mapped[list[str]] = mapped_column(JSONB)
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
