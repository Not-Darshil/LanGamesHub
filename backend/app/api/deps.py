"""Shared request helpers: context access, cookies, client IP, and auth dependencies."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection

from app.context import AppContext
from app.models import ScreenVisibility
from app.services import admin_auth, players

PLAYER_COOKIE = "lgh_player"
ADMIN_COOKIE = "lgh_admin"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "LanGamesHub"


def get_ctx(conn: HTTPConnection) -> AppContext:
    return conn.app.state.ctx


def client_ip(conn: HTTPConnection) -> str:
    # The server is reached directly on the LAN; forwarded headers are not trusted.
    return conn.client.host if conn.client else "unknown"


def same_origin(headers: Headers) -> bool:
    """Browsers always send Origin on WebSocket and cross-site requests."""
    origin = headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == headers.get("host")


def set_session_cookie(response: Response, ctx: AppContext, name: str, token: str,
                       ttl_minutes: int) -> None:
    response.set_cookie(
        name, token,
        max_age=ttl_minutes * 60,
        httponly=True,
        samesite="strict",
        secure=ctx.settings.cookie_secure,
        path="/",
    )


async def require_admin(request: Request) -> int:
    """Return the admin session id, or 401."""
    ctx = get_ctx(request)
    token = request.cookies.get(ADMIN_COOKIE)

    def check(db) -> int | None:  # noqa: ANN001
        session = admin_auth.authenticate(db, token)
        return session.id if session else None

    admin_session_id = await ctx.run(check)
    if admin_session_id is None:
        raise HTTPException(status_code=401, detail="Admin login required")
    return admin_session_id


async def require_player(request: Request) -> int:
    """Return the approved player session id, or 401/403. Also slides session expiry."""
    ctx = get_ctx(request)
    token = request.cookies.get(PLAYER_COOKIE)
    ip = client_ip(request)

    def check(db) -> tuple[int, bool]:  # noqa: ANN001
        session = players.authorize(players.find_by_token(db, token))
        players.touch(db, ctx.settings, session, ip)
        return session.id, session.screen_visibility == ScreenVisibility.HIDDEN

    session_id, hidden = await ctx.run(check)
    # Error messages can describe rooms, cards or other players; a hidden guest's
    # responses must not, so the error handler masks them (see main.py).
    request.state.screen_hidden = hidden
    return session_id
