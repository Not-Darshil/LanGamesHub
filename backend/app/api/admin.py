"""Host administration endpoints. Every route except login requires an admin session."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import TooManyRequests
from app.api.deps import (
    ADMIN_COOKIE,
    PLAYER_COOKIE,
    client_ip,
    get_ctx,
    require_admin,
    set_session_cookie,
)
from app.models import AdminSession, AdminUser, ScreenVisibility
from app.realtime.hub import CLOSE_FORBIDDEN, CLOSE_KICKED
from app.services import admin_auth, chat, players, rooms, settings_store
from app.services.errors import ServiceError
from app.services.views import build_admin_view, match_detail, session_view

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class NicknameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)


class HostPlayerRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=64)


class CreateRoomRequest(BaseModel):
    game_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    max_players: int | None = Field(default=None, ge=1, le=16)
    options: dict[str, Any] | None = None


class ScreenRequest(BaseModel):
    visibility: ScreenVisibility


class MuteRequest(BaseModel):
    muted: bool


class ChatSettingRequest(BaseModel):
    enabled: bool


class InvalidCredentials(ServiceError):
    status_code = 401


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    ctx = get_ctx(request)
    ip = client_ip(request)
    if not ctx.login_limiter.allow(ip):
        raise TooManyRequests("Too many login attempts. Wait a minute and try again.")
    token = await ctx.run(lambda db: admin_auth.login(db, ctx.settings, body.username,
                                                      body.password, ip))
    if token is None:
        raise InvalidCredentials("Invalid username or password")
    set_session_cookie(response, ctx, ADMIN_COOKIE, token, ctx.settings.admin_session_ttl_minutes)
    return {"username": body.username}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    ctx = get_ctx(request)
    token = request.cookies.get(ADMIN_COOKIE)
    await ctx.run(lambda db: admin_auth.logout(db, token))
    response.delete_cookie(ADMIN_COOKIE, path="/")
    ctx.hub.notify()
    return {"ok": True}


@router.get("/me")
async def me(request: Request, admin_session_id: int = Depends(require_admin)) -> dict:
    def load(db: Session) -> dict:
        session = db.get(AdminSession, admin_session_id)
        admin = db.get(AdminUser, session.admin_id) if session else None
        return {"username": admin.username if admin else None}

    return await get_ctx(request).run(load)


@router.get("/state")
async def state(request: Request, _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)
    return await ctx.run(lambda db: build_admin_view(db, ctx.hub.online_ids()))


@router.post("/players/{session_id}/approve")
async def approve(session_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)
    view = await ctx.run(lambda db: session_view(players.approve(db, ctx.settings, session_id)))
    ctx.hub.notify()
    return view


@router.post("/players/{session_id}/reject")
async def reject(session_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)
    view = await ctx.run(lambda db: session_view(players.reject(db, session_id)))
    await ctx.hub.close_player(session_id, CLOSE_FORBIDDEN)
    ctx.hub.notify()
    return view


@router.post("/players/{session_id}/revoke")
async def revoke(session_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)

    def revoke_session(db: Session) -> dict:
        session = players.revoke(db, session_id)
        rooms.on_session_revoked(db, session_id)  # vacates their seat; may end a game
        return session_view(session)

    view = await ctx.run(revoke_session)
    await ctx.hub.close_player(session_id, CLOSE_FORBIDDEN)
    ctx.hub.notify()
    return view


@router.post("/players/{session_id}/disconnect")
async def disconnect(session_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    """Drop the player's live connections without ending their session."""
    ctx = get_ctx(request)
    await ctx.run(lambda db: players.get_for_update(db, session_id))  # 404 if unknown
    await ctx.hub.close_player(session_id, CLOSE_KICKED)
    ctx.hub.notify()
    return {"ok": True}


@router.put("/players/{session_id}/screen")
async def set_screen(session_id: int, body: ScreenRequest, request: Request,
                     _: int = Depends(require_admin)) -> dict:
    """Guest Screen Hide / Restore Screen. Idempotent; affects only this session."""
    ctx = get_ctx(request)
    changed = await ctx.run(
        lambda db: players.set_screen_visibility(db, session_id, body.visibility))
    # Push now rather than on the next coalesced cycle so the guest's page switches
    # immediately; the push is the authenticated WebSocket delivery of the command.
    await ctx.hub.flush()
    return {"visibility": body.visibility.value, "changed": changed}


@router.put("/sound")
async def mute_everyone(body: MuteRequest, request: Request, _: int = Depends(require_admin)) -> dict:
    """Mute (or unmute) sound effects for every guest, including ones who join later."""
    ctx = get_ctx(request)
    await ctx.run(lambda db: settings_store.put(db, settings_store.MUTE_ALL_SOUND, body.muted))
    await ctx.hub.flush()
    return {"muted": body.muted}


@router.put("/chat")
async def set_chat(body: ChatSettingRequest, request: Request,
                   _: int = Depends(require_admin)) -> dict:
    """Turn room chat and reactions on or off for everyone."""
    ctx = get_ctx(request)
    await ctx.run(lambda db: settings_store.put(db, chat.CHAT_ENABLED, body.enabled))
    await ctx.hub.flush()
    return {"enabled": body.enabled}


@router.put("/players/{session_id}/sound")
async def mute_player(session_id: int, body: MuteRequest, request: Request,
                      _: int = Depends(require_admin)) -> dict:
    """Mute (or unmute) one guest's sound effects. Idempotent."""
    ctx = get_ctx(request)
    changed = await ctx.run(lambda db: players.set_sound_muted(db, session_id, body.muted))
    await ctx.hub.flush()
    return {"muted": body.muted, "changed": changed}


@router.get("/history/{match_id}")
async def history_detail(match_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    """A finished match and its final position, as a spectator sees it."""
    ctx = get_ctx(request)
    return await ctx.run(lambda db: match_detail(db, match_id, None))


@router.put("/players/{session_id}/nickname")
async def rename(session_id: int, body: NicknameRequest, request: Request,
                 _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)

    def update(db: Session) -> dict:
        session = players.authorize(players.get_for_update(db, session_id))
        return session_view(players.set_nickname(db, session, body.nickname))

    view = await ctx.run(update)
    ctx.hub.notify()
    return view


@router.post("/host-player")
async def host_player(body: HostPlayerRequest, request: Request, response: Response,
                      _: int = Depends(require_admin)) -> dict:
    """Sign this browser in as the host's player identity (separate from admin auth)."""
    ctx = get_ctx(request)
    ip = client_ip(request)
    token = await ctx.run(lambda db: players.issue_host_player(db, ctx.settings, body.nickname, ip))
    set_session_cookie(response, ctx, PLAYER_COOKIE, token,
                       ctx.settings.player_session_ttl_minutes)
    ctx.hub.notify()
    return {"ok": True}


# -- rooms -----------------------------------------------------------------------------


def _admin_username(db: Session, admin_session_id: int) -> str:
    session = db.get(AdminSession, admin_session_id)
    admin = db.get(AdminUser, session.admin_id) if session else None
    return admin.username if admin else "admin"


@router.post("/rooms", status_code=201)
async def create_room(body: CreateRoomRequest, request: Request,
                      admin_session_id: int = Depends(require_admin)) -> dict:
    """Host-created rooms are approved on creation."""
    ctx = get_ctx(request)

    def create(db: Session) -> dict:
        room = rooms.create_room(db, game_type=body.game_type, name=body.name,
                                 max_players=body.max_players, creator=None,
                                 admin_label=_admin_username(db, admin_session_id),
                                 options=body.options)
        return {"id": room.id, "status": room.status.value}

    result = await ctx.run(create)
    ctx.hub.notify()
    return result


async def _room_op(request: Request, op) -> dict:  # noqa: ANN001
    ctx = get_ctx(request)
    room_status = await ctx.run(lambda db: op(db).status.value)
    ctx.hub.notify()
    return {"status": room_status}


@router.post("/rooms/{room_id}/approve")
async def approve_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    return await _room_op(request, lambda db: rooms.approve_room(db, room_id))


@router.post("/rooms/{room_id}/lock")
async def lock_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    return await _room_op(request, lambda db: rooms.set_locked(db, room_id, True))


@router.post("/rooms/{room_id}/unlock")
async def unlock_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    return await _room_op(request, lambda db: rooms.set_locked(db, room_id, False))


@router.post("/rooms/{room_id}/start")
async def start_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    """Explicit host confirmation; the only way a game ever starts."""
    ctx = get_ctx(request)
    online = ctx.hub.online_ids()
    return await _room_op(request, lambda db: rooms.start_room(db, room_id, online, ctx.rng))


@router.post("/rooms/{room_id}/finish")
async def finish_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    return await _room_op(request, lambda db: rooms.finish_room(db, room_id))


@router.post("/rooms/{room_id}/cancel")
async def cancel_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    return await _room_op(request, lambda db: rooms.cancel_room(db, room_id))


@router.delete("/rooms/{room_id}")
async def delete_room(room_id: int, request: Request, _: int = Depends(require_admin)) -> dict:
    ctx = get_ctx(request)
    await ctx.run(lambda db: rooms.delete_room(db, room_id))
    ctx.hub.notify()
    return {"ok": True}
