"""Room chat and emoji reactions. Only members of a room can post or read its chat."""

from __future__ import annotations

import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlayerSession, Room, RoomMessage
from app.services import players, settings_store
from app.services.errors import Forbidden, NotFound, ServiceError
from app.timeutil import utcnow

MESSAGE_MAX = 300
HISTORY = 60          # chat lines sent with the room view
RECENT_REACTIONS = 12  # reactions sent with the room view (clients animate new ones)
REACTIONS = ("👍", "😂", "😮", "😢", "🔥", "👏", "🎉", "😡", "❤️", "🤯")
CHAT_ENABLED = "chat_enabled"


class ChatDisabled(ServiceError):
    status_code = 409


def chat_enabled(db: Session) -> bool:
    return bool(settings_store.get(db, CHAT_ENABLED, True))


def clean_text(raw: str) -> str:
    """Strip control characters, collapse whitespace, and enforce the length limit."""
    text = "".join(ch for ch in raw if unicodedata.category(ch) != "Cc" or ch in "\n\t")
    text = " ".join(text.split())
    if not text:
        raise ServiceError("Type a message first")
    if len(text) > MESSAGE_MAX:
        raise ServiceError(f"Messages can be at most {MESSAGE_MAX} characters")
    return text


def _member_room(db: Session, session_id: int, room_id: int) -> tuple[PlayerSession, Room]:
    session = players.authorize(db.get(PlayerSession, session_id))
    room = db.get(Room, room_id)
    if room is None:
        raise NotFound("Room not found")
    if not any(m.session_id == session_id for m in room.members):
        raise Forbidden("You are not in this room")
    if not chat_enabled(db):
        raise ChatDisabled("The host has turned chat off")
    return session, room


def post(db: Session, session_id: int, room_id: int, kind: str, body: str) -> RoomMessage:
    session, room = _member_room(db, session_id, room_id)
    if kind == "text":
        body = clean_text(body)
    elif kind == "reaction":
        if body not in REACTIONS:
            raise ServiceError("Unknown reaction")
    else:
        raise ServiceError("Unknown message kind")
    message = RoomMessage(room_id=room.id, session_id=session.id,
                          nickname=session.nickname or "Player", kind=kind, body=body,
                          created_at=utcnow())
    db.add(message)
    db.flush()
    return message


def recent(db: Session, room_ids: list[int]) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """The latest chat lines and reactions of each room, oldest first, in one query."""
    out: dict[int, dict[str, list[dict[str, Any]]]] = {
        rid: {"messages": [], "reactions": []} for rid in room_ids}
    if not room_ids:
        return out
    rank = func.row_number().over(partition_by=(RoomMessage.room_id, RoomMessage.kind),
                                  order_by=RoomMessage.id.desc()).label("rank")
    inner = select(RoomMessage, rank).where(RoomMessage.room_id.in_(room_ids)).subquery()
    rows = db.execute(
        select(inner).where(
            ((inner.c.kind == "text") & (inner.c.rank <= HISTORY))
            | ((inner.c.kind == "reaction") & (inner.c.rank <= RECENT_REACTIONS)))
        .order_by(inner.c.id)).all()
    for row in rows:
        entry = {"id": row.id, "from": str(row.session_id) if row.session_id else "",
                 "nickname": row.nickname, "at": row.created_at.isoformat()}
        if row.kind == "text":
            out[row.room_id]["messages"].append({**entry, "text": row.body})
        else:
            out[row.room_id]["reactions"].append({**entry, "emoji": row.body})
    return out
