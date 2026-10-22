"""Builds what each connected client may see. This is the data-exposure boundary.

Player views contain only that player's session, the lobby (room summaries), and their
own room/game, with hidden information filtered by the game engine. Room details and
game state are never sent to non-members. The admin view contains session and room
metadata but never game state, because the host may also be playing.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.games.registry import catalog, get_engine
from app.models import (
    ACTIVE_STATUSES,
    AdminSession,
    MatchResult,
    PlayerSession,
    Room,
    RoomMember,
    RoomStatus,
    ScreenVisibility,
    SessionStatus,
)
from app.realtime.hub import CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED, PlayerPush, Snapshot
from app.services.players import EXPIRED, effective_status
from app.services.rooms import participant_names, player_key
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

# Finished rooms and rejected/revoked sessions stay visible to the admin this long.
RECENT_HISTORY = timedelta(hours=12)
LOBBY_STATUSES = (RoomStatus.WAITING_FOR_PLAYERS, RoomStatus.READY_TO_START,
                  RoomStatus.IN_PROGRESS)


def session_view(session: PlayerSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "status": effective_status(session),
        "nickname": session.nickname,
        "is_host": session.is_host,
        "screen": session.screen_visibility.value,
    }


def is_hidden(session: PlayerSession) -> bool:
    return session.screen_visibility == ScreenVisibility.HIDDEN


def hidden_view(session: PlayerSession) -> dict[str, Any]:
    """All a hidden guest's browser receives: no names, rooms, boards or activity."""
    return {"session": {"id": session.id, "status": effective_status(session),
                        "screen": ScreenVisibility.HIDDEN.value}}


def own_session_view(session: PlayerSession) -> dict[str, Any]:
    """The player's own /api/me payload, respecting Guest Screen Hide."""
    return hidden_view(session)["session"] if is_hidden(session) else session_view(session)


def games_view() -> list[dict[str, Any]]:
    return [
        {"game_type": g.game_type, "name": g.name, "min_players": g.min_players,
         "max_players": g.max_players, "description": g.description}
        for g in catalog()
    ]


def room_summary(room: Room) -> dict[str, Any]:
    engine = get_engine(room.game_type)
    return {
        "id": room.id,
        "name": room.name,
        "game_type": room.game_type,
        "game_name": engine.info.name if engine else room.game_type,
        "status": room.status.value,
        "players": len(room.members),
        "min_players": engine.info.min_players if engine else None,
        "max_players": room.max_players,
        "is_locked": room.is_locked,
        "creator": room.creator_label,
        "options": room.options or {},
        "options_label": engine.options_label(room.options or {}) if engine else None,
    }


class _Loaded:
    """Rows shared by every view in one push, loaded once."""

    def __init__(self, db: Session, session_ids: set[int], online: set[int],
                 include_admin: bool) -> None:
        now = utcnow()
        self.online = online
        member_room_ids = select(RoomMember.room_id).where(RoomMember.session_id.in_(session_ids))
        room_filter = or_(Room.status.in_(ACTIVE_STATUSES), Room.id.in_(member_room_ids))
        if include_admin:
            room_filter = or_(room_filter, Room.finished_at > now - RECENT_HISTORY)
        self.rooms: dict[int, Room] = {
            r.id: r for r in db.scalars(
                select(Room).where(room_filter).options(selectinload(Room.members))
                .order_by(Room.created_at))
        }
        member_ids = {m.session_id for r in self.rooms.values() for m in r.members}
        self.sessions: dict[int, PlayerSession] = {
            s.id: s for s in db.scalars(
                select(PlayerSession).where(PlayerSession.id.in_(member_ids | session_ids)))
        }
        # A player's room: the active one, else the most recently finished one not left.
        self.room_of: dict[int, Room] = {}
        for room in sorted(self.rooms.values(),
                           key=lambda r: (r.status in ACTIVE_STATUSES, r.finished_at or now)):
            for member in room.members:
                self.room_of[member.session_id] = room
        self.results: dict[int, MatchResult] = {
            r.room_id: r for r in db.scalars(
                select(MatchResult).where(MatchResult.room_id.in_(list(self.rooms)))
                .order_by(MatchResult.id))
            if r.room_id is not None
        }

    def nickname(self, session_id: int) -> str:
        session = self.sessions.get(session_id)
        return (session.nickname if session else None) or f"Player {session_id}"

    def members_view(self, room: Room) -> list[dict[str, Any]]:
        return [
            {"session_id": m.session_id, "nickname": self.nickname(m.session_id),
             "seat": m.seat, "is_ready": m.is_ready, "online": m.session_id in self.online,
             "is_host": bool(self.sessions.get(m.session_id)
                             and self.sessions[m.session_id].is_host)}
            for m in room.members
        ]

    def result_view(self, room: Room) -> dict[str, Any] | None:
        result = self.results.get(room.id)
        if result is None:
            return None
        return {"outcome": result.outcome, "winners": result.winners, "reason": result.reason}

    def awaiting(self, room: Room) -> list[str]:
        engine = get_engine(room.game_type)
        if room.status != RoomStatus.IN_PROGRESS or engine is None or room.game_state is None:
            return []
        names = participant_names(room)
        return [names.get(p, p) for p in engine.awaiting(room.game_state)]


def player_view(loaded: _Loaded, session: PlayerSession) -> dict[str, Any]:
    if is_hidden(session):
        return hidden_view(session)
    view: dict[str, Any] = {"session": session_view(session)}
    if effective_status(session) != SessionStatus.APPROVED:
        return view  # pending guests learn nothing beyond their own status

    view["lobby"] = {
        "games": games_view(),
        "rooms": [
            room_summary(r) for r in loaded.rooms.values()
            if r.status in LOBBY_STATUSES
            or (r.status == RoomStatus.CREATED and r.creator_session_id == session.id)
        ],
    }
    room = loaded.room_of.get(session.id)
    view["room"] = None
    view["game"] = None
    if room is not None:
        view["room"] = {
            **room_summary(room),
            "members": loaded.members_view(room),
            "status_reason": room.status_reason,
            "result": loaded.result_view(room),
            "awaiting": loaded.awaiting(room),
        }
        engine = get_engine(room.game_type)
        if engine is not None and room.game_state is not None:
            view["game"] = {
                "version": room.state_version,
                "names": participant_names(room),
                "you": player_key(session.id),
                **engine.view(room.game_state, player_key(session.id)),
            }
    return view


def player_push(loaded: _Loaded, session: PlayerSession | None) -> PlayerPush:
    if session is None:
        return PlayerPush(close_code=CLOSE_UNAUTHENTICATED)
    status = effective_status(session)
    if status == EXPIRED:
        return PlayerPush(close_code=CLOSE_UNAUTHENTICATED)
    if status in (SessionStatus.REJECTED, SessionStatus.REVOKED):
        return PlayerPush(close_code=CLOSE_FORBIDDEN)
    try:
        return PlayerPush(view=player_view(loaded, session))
    except Exception:
        # Isolate failures: this player gets their bare session; everyone else is unaffected.
        logger.exception("Building the view for player session %s failed", session.id)
        return PlayerPush(view=hidden_view(session) if is_hidden(session)
                          else {"session": session_view(session)})


def build_player_view(db: Session, session_id: int, online: set[int]) -> dict[str, Any]:
    loaded = _Loaded(db, {session_id}, online, include_admin=False)
    return player_view(loaded, loaded.sessions[session_id])


def build_snapshot(db: Session, online: set[int], admin_session_ids: set[int]) -> Snapshot:
    now = utcnow()
    valid_admins = set(db.scalars(select(AdminSession.id).where(
        AdminSession.id.in_(admin_session_ids),
        AdminSession.revoked_at.is_(None),
        AdminSession.expires_at > now,
    ))) if admin_session_ids else set()
    loaded = _Loaded(db, online, online, include_admin=bool(valid_admins))
    players = {sid: player_push(loaded, loaded.sessions.get(sid)) for sid in online}
    admin_view = _admin_view(db, loaded) if valid_admins else None
    return Snapshot(players=players, admin_view=admin_view, valid_admin_sessions=valid_admins)


def build_admin_view(db: Session, online: set[int]) -> dict[str, Any]:
    return _admin_view(db, _Loaded(db, set(), online, include_admin=True))


def _admin_view(db: Session, loaded: _Loaded) -> dict[str, Any]:
    now = utcnow()
    rows = db.scalars(
        select(PlayerSession)
        .where(
            (PlayerSession.status.in_([SessionStatus.PENDING, SessionStatus.APPROVED])
             & (PlayerSession.expires_at > now))
            | (PlayerSession.status.in_([SessionStatus.REJECTED, SessionStatus.REVOKED])
               & (PlayerSession.decided_at > now - RECENT_HISTORY))
        )
        .order_by(PlayerSession.created_at)
    ).all()
    rejected_by_ip = dict(db.execute(
        select(PlayerSession.ip_address, func.count())
        .where(PlayerSession.status == SessionStatus.REJECTED)
        .group_by(PlayerSession.ip_address)
    ).all())

    pending, player_rows = [], []
    for s in rows:
        room = loaded.room_of.get(s.id)
        entry = {
            **session_view(s),
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat(),
            "online": s.id in loaded.online,
            "room": None if room is None else
            {"id": room.id, "name": room.name, "status": room.status.value},
        }
        if s.status == SessionStatus.PENDING:
            entry["prior_rejections"] = rejected_by_ip.get(s.ip_address, 0)
            pending.append(entry)
        else:
            player_rows.append(entry)

    rooms = [
        {
            **room_summary(r),
            "approved": r.approved_at is not None,
            "members": loaded.members_view(r),
            "status_reason": r.status_reason,
            "awaiting": loaded.awaiting(r),
            "result": loaded.result_view(r),
            "created_at": r.created_at.isoformat(),
        }
        for r in loaded.rooms.values()
    ]
    history = [
        {"id": m.id, "room_name": m.room_name, "game_type": m.game_type, "outcome": m.outcome,
         "winners": m.winners, "reason": m.reason,
         "participants": [p["nickname"] for p in m.participants],
         "finished_at": m.finished_at.isoformat()}
        for m in db.scalars(select(MatchResult).order_by(MatchResult.id.desc()).limit(20))
    ]
    return {"pending": pending, "players": player_rows, "rooms": rooms,
            "games": games_view(), "history": history}
