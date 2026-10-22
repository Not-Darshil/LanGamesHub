"""Room lifecycle and membership: the room state machine.

    CREATED ──approve──▶ WAITING_FOR_PLAYERS ◀──auto──▶ READY_TO_START ──host start──▶ IN_PROGRESS
       │                        │                              │                          │
       └──────────── cancel ────┴──────────────────────────────┴──── cancel ──────────────┤
                                                                                           ▼
                                        CANCELLED                     COMPLETED ◀── game over / host finish

* WAITING ⇄ READY is recomputed after every membership/readiness change: READY means at
  least the game's minimum players have joined and every member is ready. Reaching
  READY never starts the game; only the host's explicit Start does.
* Start additionally requires every member to be connected right now.
* ``is_locked`` freezes membership (no joins/leaves) before start; started rooms are
  implicitly locked.
* A member who stays disconnected past the grace period loses their ready flag
  (READY → WAITING). Disconnects never alter an IN_PROGRESS game; it waits for them.

Concurrency: every mutation runs in one transaction holding row locks, always taken in
the order player session → room, so joins, leaves, and starts cannot race.
"""

from __future__ import annotations

import logging
import random
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.games.base import Action, GameEngine, Options, Outcome
from app.games.registry import GAMES
from app.games.registry import get_engine
from app.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    MatchResult,
    PlayerSession,
    Room,
    RoomMember,
    RoomStatus,
)
from app.services import players
from app.services.errors import Conflict, Forbidden, NotFound, ServiceError
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

ROOM_NAME_MAX = 40
JOINABLE = (RoomStatus.WAITING_FOR_PLAYERS, RoomStatus.READY_TO_START)
PRE_START = (RoomStatus.CREATED, *JOINABLE)


def engine_for(room: Room) -> GameEngine:
    engine = get_engine(room.game_type)
    if engine is None:
        raise ServiceError(f"Game type {room.game_type!r} is not available")
    return engine


def player_key(session_id: int) -> str:
    return str(session_id)


def _normalize_name(raw: str) -> str:
    name = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not name:
        raise ServiceError("Room name cannot be empty")
    if len(name) > ROOM_NAME_MAX:
        raise ServiceError(f"Room name must be at most {ROOM_NAME_MAX} characters")
    return name


def _lock_room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id, with_for_update=True, populate_existing=True)
    if room is None:
        raise NotFound("Room not found")
    return room


def active_membership(db: Session, session_id: int) -> RoomMember | None:
    """The member row of the room this player is currently in (at most one)."""
    return db.scalar(
        select(RoomMember).join(Room)
        .where(RoomMember.session_id == session_id, Room.status.in_(ACTIVE_STATUSES))
    )


def current_membership(db: Session, session_id: int) -> RoomMember | None:
    """Active room membership, else the latest finished room not yet left."""
    return active_membership(db, session_id) or db.scalar(
        select(RoomMember).join(Room)
        .where(RoomMember.session_id == session_id)
        .order_by(Room.finished_at.desc().nulls_last(), RoomMember.id.desc())
    )


def _recompute(room: Room) -> None:
    if room.status not in JOINABLE:
        return
    engine = engine_for(room)
    members = room.members
    ready = len(members) >= engine.info.min_players and all(m.is_ready for m in members)
    room.status = RoomStatus.READY_TO_START if ready else RoomStatus.WAITING_FOR_PLAYERS


def _leave_finished_rooms(db: Session, session_id: int) -> None:
    for member in db.scalars(select(RoomMember).join(Room).where(
            RoomMember.session_id == session_id, Room.status.in_(TERMINAL_STATUSES))):
        db.delete(member)
    db.flush()


def _seat_member(db: Session, room: Room, session_id: int) -> RoomMember:
    taken = {m.seat for m in room.members}
    seat = next(s for s in range(room.max_players) if s not in taken)
    member = RoomMember(room_id=room.id, session_id=session_id, seat=seat, is_ready=False,
                        joined_at=utcnow())
    room.members.append(member)
    db.flush()
    return member


# -- creation and host controls --------------------------------------------------------


def create_room(db: Session, *, game_type: str, name: str, max_players: int | None,
                creator: PlayerSession | None, admin_label: str | None = None,
                options: Options | None = None) -> Room:
    """Create a room. Admin-created rooms are approved immediately; a player's proposal
    starts in CREATED with the proposer seated, until the host approves it."""
    engine = get_engine(game_type)
    if engine is None:
        raise ServiceError("Unknown game type")
    info = engine.info
    limit = info.max_players if max_players is None else max_players
    if not info.min_players <= limit <= info.max_players:
        raise ServiceError(
            f"{info.name} supports {info.min_players}–{info.max_players} players")
    options = engine.validate_options(options)  # GameError is a 400 ServiceError
    now = utcnow()
    by_admin = creator is None
    if creator is not None:
        creator = players.authorize(players.get_for_update(db, creator.id))
        if creator.nickname is None:
            raise ServiceError("Choose a nickname first")
        if active_membership(db, creator.id) is not None:
            raise Conflict("Leave your current room before creating another")
        _leave_finished_rooms(db, creator.id)
    room = Room(
        name=_normalize_name(name),
        game_type=game_type,
        status=RoomStatus.WAITING_FOR_PLAYERS if by_admin else RoomStatus.CREATED,
        max_players=limit,
        options=options,
        is_locked=False,
        created_by_admin=by_admin,
        creator_session_id=None if creator is None else creator.id,
        creator_label=f"host ({admin_label})" if by_admin else (creator.nickname or "guest"),
        approved_at=now if by_admin else None,
        state_version=0,
        created_at=now,
    )
    db.add(room)
    db.flush()
    if creator is not None:
        _seat_member(db, room, creator.id)
    logger.info("Room %s (%s) created by %s", room.id, game_type, room.creator_label)
    return room


def approve_room(db: Session, room_id: int) -> Room:
    room = _lock_room(db, room_id)
    if room.status == RoomStatus.CREATED:
        room.status = RoomStatus.WAITING_FOR_PLAYERS
        room.approved_at = utcnow()
        _recompute(room)
    elif room.status not in JOINABLE:
        raise Conflict("Only proposed rooms can be approved")
    return room


def set_locked(db: Session, room_id: int, locked: bool) -> Room:
    room = _lock_room(db, room_id)
    if room.status not in PRE_START:
        raise Conflict("Only rooms that have not started can be locked or unlocked")
    room.is_locked = locked
    return room


def start_room(db: Session, room_id: int, online: set[int], rng: random.Random) -> Room:
    """The host's explicit Start. Re-validates every precondition under the room lock."""
    room = _lock_room(db, room_id)
    engine = engine_for(room)
    if room.status == RoomStatus.IN_PROGRESS:
        raise Conflict("The game has already started")
    if room.approved_at is None or room.status == RoomStatus.CREATED:
        raise Conflict("Approve the room before starting it")
    if room.status != RoomStatus.READY_TO_START:
        raise Conflict("Not every required player has joined and is ready")
    members = list(room.members)
    if not engine.info.min_players <= len(members) <= min(room.max_players,
                                                          engine.info.max_players):
        raise Conflict("The room does not have a valid number of players")
    offline = [m for m in members if m.session_id not in online]
    if offline:
        names = ", ".join(_nickname(db, m.session_id) for m in offline)
        raise Conflict(f"Waiting for {names} to connect")
    for member in members:
        session = db.get(PlayerSession, member.session_id)
        if session is None or players.effective_status(session) != "APPROVED":
            raise Conflict(f"{_nickname(db, member.session_id)} is no longer authorized")
    room.participants = [
        {"id": player_key(m.session_id), "session_id": m.session_id,
         "nickname": _nickname(db, m.session_id), "seat": m.seat}
        for m in members
    ]
    room.game_state = engine.start([player_key(m.session_id) for m in members], rng,
                                   room.options or {})
    room.state_version += 1
    room.status = RoomStatus.IN_PROGRESS
    room.is_locked = True
    room.started_at = utcnow()
    logger.info("Room %s started with %d players", room.id, len(members))
    return room


def finish_room(db: Session, room_id: int) -> Room:
    """Host ends a running match early. Recorded as ABORTED."""
    room = _lock_room(db, room_id)
    if room.status != RoomStatus.IN_PROGRESS:
        raise Conflict("Only a game in progress can be finished")
    _complete(db, room, Outcome(winners=[], reason="Ended by the host"), aborted=True)
    return room


def cancel_room(db: Session, room_id: int, reason: str = "Cancelled by the host") -> Room:
    room = _lock_room(db, room_id)
    if room.status in TERMINAL_STATUSES:
        return room
    _cancel(db, room, reason)
    return room


def delete_room(db: Session, room_id: int) -> None:
    room = _lock_room(db, room_id)
    if room.status not in TERMINAL_STATUSES:
        _cancel(db, room, "Removed by the host")
    db.delete(room)
    logger.info("Room %s removed", room_id)


def _cancel(db: Session, room: Room, reason: str) -> None:
    if room.status == RoomStatus.IN_PROGRESS:
        _record_result(db, room, "CANCELLED", [], reason)
    room.status = RoomStatus.CANCELLED
    room.status_reason = reason
    room.finished_at = utcnow()


# -- player membership -----------------------------------------------------------------


def join_room(db: Session, session_id: int, room_id: int) -> Room:
    session = players.authorize(players.get_for_update(db, session_id))
    if session.nickname is None:
        raise ServiceError("Choose a nickname first")
    room = _lock_room(db, room_id)
    existing = active_membership(db, session_id)
    if existing is not None:
        if existing.room_id == room_id:
            return room
        raise Conflict("Leave your current room first")
    if room.status not in JOINABLE:
        raise Conflict("This room is not accepting players")
    if room.is_locked:
        raise Conflict("This room is locked")
    if len(room.members) >= room.max_players:
        raise Conflict("This room is full")
    _leave_finished_rooms(db, session_id)
    _seat_member(db, room, session_id)
    _recompute(room)
    return room


def leave_room(db: Session, session_id: int, room_id: int, *, force: bool = False) -> Room:
    """Leave a room. Leaving a game in progress forfeits; ``force`` bypasses the lock
    (used when the host revokes a session)."""
    players.get_for_update(db, session_id)
    room = _lock_room(db, room_id)
    member = next((m for m in room.members if m.session_id == session_id), None)
    if member is None:
        raise NotFound("You are not in this room")
    if room.is_locked and room.status in PRE_START and not force:
        raise Conflict("This room is locked")

    if room.status == RoomStatus.IN_PROGRESS:
        engine = engine_for(room)
        assert room.game_state is not None
        room.game_state = engine.remove_player(room.game_state, player_key(session_id))
        room.state_version += 1
        room.members.remove(member)
        db.flush()
        outcome = engine.outcome(room.game_state)
        if outcome is not None:
            _complete(db, room, outcome)
        return room

    room.members.remove(member)
    db.flush()
    if room.status == RoomStatus.CREATED and session_id == room.creator_session_id:
        _cancel(db, room, "The player who proposed it left")
    _recompute(room)
    return room


def set_ready(db: Session, session_id: int, room_id: int, ready: bool) -> Room:
    players.authorize(players.get_for_update(db, session_id))
    room = _lock_room(db, room_id)
    member = next((m for m in room.members if m.session_id == session_id), None)
    if member is None:
        raise NotFound("You are not in this room")
    if room.status not in PRE_START:
        raise Conflict("Readiness can only change before the game starts")
    member.is_ready = ready
    _recompute(room)
    return room


def apply_action(db: Session, session_id: int, room_id: int, action: Action,
                 rng: random.Random) -> Room:
    players.authorize(db.get(PlayerSession, session_id))
    room = _lock_room(db, room_id)
    if not any(m.session_id == session_id for m in room.members):
        raise Forbidden("You are not in this room")
    if room.status != RoomStatus.IN_PROGRESS or room.game_state is None:
        raise Conflict("The game is not in progress")
    engine = engine_for(room)
    room.game_state = engine.apply(room.game_state, player_key(session_id), action, rng)
    room.state_version += 1
    outcome = engine.outcome(room.game_state)
    if outcome is not None:
        _complete(db, room, outcome)
    return room


def expire_clocks(db: Session) -> bool:
    """End timed games whose clock has run out with nobody acting. Returns True if any did.

    Runs periodically; a move that arrives after the flag fell is also caught by the
    engine itself, so this only bounds how long a finished game can look unfinished.
    """
    timed = [game_type for game_type, engine in GAMES.items() if engine.timed]
    if not timed:
        return False
    candidates = db.execute(
        select(Room.id, Room.game_type, Room.game_state)
        .where(Room.status == RoomStatus.IN_PROGRESS, Room.game_type.in_(timed))
    ).all()
    changed = False
    for room_id, game_type, state in candidates:
        engine = GAMES[game_type]
        due = engine.deadline(state) if state else None
        if due is None or engine.now() < due:
            continue
        room = _lock_room(db, room_id)
        if room.status != RoomStatus.IN_PROGRESS or room.game_state is None:
            continue
        new_state = engine.expire(room.game_state)
        if new_state is room.game_state:
            continue
        room.game_state = new_state
        room.state_version += 1
        outcome = engine.outcome(new_state)
        if outcome is not None:
            _complete(db, room, outcome)
        changed = True
    return changed


# -- reactions to session events -------------------------------------------------------


def on_session_revoked(db: Session, session_id: int) -> None:
    member = active_membership(db, session_id)
    if member is not None:
        leave_room(db, session_id, member.room_id, force=True)


def on_player_offline(db: Session, session_id: int) -> bool:
    """Clear the ready flag of a member who stayed disconnected. Returns True if changed."""
    member = active_membership(db, session_id)
    if member is None:
        return False
    room = _lock_room(db, member.room_id)
    member = next((m for m in room.members if m.session_id == session_id), None)
    if member is None or room.status not in JOINABLE or not member.is_ready:
        return False
    member.is_ready = False
    _recompute(room)
    return True


# -- completion ------------------------------------------------------------------------


def _complete(db: Session, room: Room, outcome: Outcome, *, aborted: bool = False) -> None:
    names = {p["id"]: p["nickname"] for p in room.participants or []}
    winners = [names.get(w, w) for w in outcome.winners]
    kind = "ABORTED" if aborted else ("DRAW" if outcome.draw else "WIN")
    _record_result(db, room, kind, winners, outcome.reason)
    room.status = RoomStatus.COMPLETED
    room.status_reason = outcome.reason or None
    room.finished_at = utcnow()
    logger.info("Room %s completed: %s %s", room.id, kind, winners)


def _record_result(db: Session, room: Room, kind: str, winners: list[str], reason: str) -> None:
    db.add(MatchResult(
        room_id=room.id,
        room_name=room.name,
        game_type=room.game_type,
        outcome=kind,
        winners=winners,
        participants=room.participants or [],
        reason=reason[:200],
        started_at=room.started_at,
        finished_at=utcnow(),
    ))


def _nickname(db: Session, session_id: int) -> str:
    session = db.get(PlayerSession, session_id)
    return (session.nickname if session else None) or f"Player {session_id}"


def participant_names(room: Room) -> dict[str, Any]:
    return {p["id"]: p["nickname"] for p in room.participants or []}
