"""Player-facing room endpoints and the REST fallback for the player's full view."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import TooManyRequests
from app.api.deps import get_ctx, require_player
from app.models import PlayerSession
from app.services import rooms
from app.services.views import build_player_view, match_detail, player_history

router = APIRouter(prefix="/api", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    game_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    max_players: int | None = Field(default=None, ge=1, le=16)
    options: dict[str, Any] | None = None


class ReadyRequest(BaseModel):
    ready: bool


class ActionRequest(BaseModel):
    action: dict[str, Any]


@router.get("/state")
async def state(request: Request, session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)
    return await ctx.run(lambda db: build_player_view(db, session_id, ctx.hub.online_ids()))


@router.post("/rooms", status_code=201)
async def propose_room(body: CreateRoomRequest, request: Request,
                       session_id: int = Depends(require_player)) -> dict:
    """A player proposes a room; it stays CREATED until the host approves it."""
    ctx = get_ctx(request)

    def create(db: Session) -> dict:
        creator = db.get(PlayerSession, session_id)
        room = rooms.create_room(db, game_type=body.game_type, name=body.name,
                                 max_players=body.max_players, creator=creator,
                                 options=body.options)
        return {"id": room.id, "status": room.status.value}

    result = await ctx.run(create)
    ctx.hub.notify()
    return result


@router.post("/rooms/{room_id}/join")
async def join(room_id: int, request: Request, session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)
    room_status = await ctx.run(lambda db: rooms.join_room(db, session_id, room_id).status.value)
    ctx.hub.notify()
    return {"status": room_status}


@router.post("/rooms/{room_id}/leave")
async def leave(room_id: int, request: Request, session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)
    room_status = await ctx.run(lambda db: rooms.leave_room(db, session_id, room_id).status.value)
    ctx.hub.notify()
    return {"status": room_status}


@router.post("/rooms/{room_id}/ready")
async def ready(room_id: int, body: ReadyRequest, request: Request,
                session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)
    room_status = await ctx.run(
        lambda db: rooms.set_ready(db, session_id, room_id, body.ready).status.value)
    ctx.hub.notify()
    return {"status": room_status}


@router.post("/rooms/{room_id}/actions")
async def act(room_id: int, body: ActionRequest, request: Request,
              session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)
    if not ctx.action_limiter.allow(str(session_id)):
        raise TooManyRequests("Slow down")

    def apply(db: Session) -> dict:
        room = rooms.apply_action(db, session_id, room_id, body.action, ctx.rng)
        return {"status": room.status.value, "version": room.state_version}

    result = await ctx.run(apply)
    ctx.hub.notify()
    return result


@router.get("/history")
async def history(request: Request, session_id: int = Depends(require_player)) -> dict:
    """Finished matches this player took part in."""
    ctx = get_ctx(request)
    return {"matches": await ctx.run(lambda db: player_history(db, session_id))}


@router.get("/history/{match_id}")
async def history_detail(match_id: int, request: Request,
                         session_id: int = Depends(require_player)) -> dict:
    """One finished match, with the final position as this player saw it."""
    ctx = get_ctx(request)
    return await ctx.run(lambda db: match_detail(db, match_id, session_id))
