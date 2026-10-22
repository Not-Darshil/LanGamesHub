"""Guest-facing endpoints: request access with the shared password, view own session."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import PLAYER_COOKIE, client_ip, get_ctx, require_player, set_session_cookie
from app.models import SessionStatus
from app.security import check_room_password
from app.services import players
from app.services.errors import Forbidden, ServiceError
from app.services.views import own_session_view, session_view

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["access"])


class AccessRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class NicknameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)


class SoundRequest(BaseModel):
    enabled: bool


class TooManyRequests(ServiceError):
    status_code = 429


class InvalidPassword(ServiceError):
    status_code = 401


@router.post("/access/request", status_code=201)
async def request_access(body: AccessRequest, request: Request, response: Response) -> dict:
    ctx = get_ctx(request)
    ip = client_ip(request)
    existing_token = request.cookies.get(PLAYER_COOKIE)

    def existing(db) -> dict | None:  # noqa: ANN001
        session = players.find_by_token(db, existing_token)
        if session is None or players.effective_status(session) == players.EXPIRED:
            return None
        return own_session_view(session)

    # A browser that already has a live or decided session keeps it: asking again
    # must not let a rejected guest start over with the same cookie.
    current = await ctx.run(existing)
    if current is not None:
        if current["status"] in (SessionStatus.REJECTED, SessionStatus.REVOKED):
            raise Forbidden("Forbidden")
        return current

    if not ctx.access_limiter.allow(ip):
        raise TooManyRequests("Too many attempts. Wait a minute and try again.")
    if not check_room_password(ctx.settings, body.password):
        logger.warning("Wrong room password from %s", ip)
        raise InvalidPassword("Incorrect password")

    user_agent = request.headers.get("user-agent", "")

    def create(db) -> tuple[str, dict]:  # noqa: ANN001
        token, session = players.request_access(db, ctx.settings, ip, user_agent)
        return token, session_view(session)

    token, view = await ctx.run(create)
    set_session_cookie(response, ctx, PLAYER_COOKIE, token,
                       ctx.settings.player_session_ttl_minutes)
    ctx.hub.notify()
    return view


@router.get("/me")
async def me(request: Request) -> dict:
    ctx = get_ctx(request)
    token = request.cookies.get(PLAYER_COOKIE)
    ip = client_ip(request)

    def load(db) -> dict:  # noqa: ANN001
        session = players.authorize(players.find_by_token(db, token), allow_pending=True)
        if session.status == SessionStatus.APPROVED:
            players.touch(db, ctx.settings, session, ip)
        return own_session_view(session)

    return await ctx.run(load)


@router.put("/me/nickname")
async def set_nickname(body: NicknameRequest, request: Request,
                       session_id: int = Depends(require_player)) -> dict:
    ctx = get_ctx(request)

    def update(db) -> dict:  # noqa: ANN001
        session = players.get_for_update(db, session_id)
        return own_session_view(players.guest_set_nickname(db, session, body.nickname))

    view = await ctx.run(update)
    ctx.hub.notify()
    return view


@router.put("/me/sound")
async def report_sound(body: SoundRequest, request: Request,
                       session_id: int = Depends(require_player)) -> dict:
    """The browser reports its sound setting so the host can see whose audio is on."""
    ctx = get_ctx(request)
    if await ctx.run(lambda db: players.report_sound(db, session_id, body.enabled)):
        ctx.hub.notify()
    return {"enabled": body.enabled}
