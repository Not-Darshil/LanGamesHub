"""WebSocket endpoints. Authentication happens at the handshake via HttpOnly cookies,
and the hub re-checks authorization on every push."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_COOKIE, PLAYER_COOKIE, client_ip, get_ctx, same_origin
from app.realtime.hub import CLOSE_FORBIDDEN, CLOSE_TOO_MANY, CLOSE_UNAUTHENTICATED, Connection
from app.services import admin_auth, players
from app.services.errors import Forbidden, ServiceError

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_BYTES = 1024


@router.websocket("/ws/player")
async def player_socket(ws: WebSocket) -> None:
    ctx = get_ctx(ws)
    if not same_origin(ws.headers):
        await ws.close(code=CLOSE_FORBIDDEN)
        return
    token = ws.cookies.get(PLAYER_COOKIE)
    ip = client_ip(ws)

    def check(db: Session) -> int:
        session = players.authorize(players.find_by_token(db, token), allow_pending=True)
        players.touch(db, ctx.settings, session, ip)
        return session.id

    try:
        session_id = await ctx.run(check)
    except ServiceError as exc:
        await ws.accept()
        code = CLOSE_FORBIDDEN if isinstance(exc, Forbidden) else CLOSE_UNAUTHENTICATED
        await ws.close(code=code)
        return

    await ws.accept()
    if not ctx.hub.has_capacity(session_id):
        await ws.close(code=CLOSE_TOO_MANY)
        return
    conn = await ctx.hub.add_player(session_id, ws)
    try:
        await _receive_loop(ws, conn)
    finally:
        await ctx.hub.remove_player(session_id, conn)


@router.websocket("/ws/admin")
async def admin_socket(ws: WebSocket) -> None:
    ctx = get_ctx(ws)
    if not same_origin(ws.headers):
        await ws.close(code=CLOSE_FORBIDDEN)
        return
    token = ws.cookies.get(ADMIN_COOKIE)

    def check(db: Session) -> int | None:
        session = admin_auth.authenticate(db, token)
        return session.id if session else None

    admin_session_id = await ctx.run(check)
    await ws.accept()
    if admin_session_id is None:
        await ws.close(code=CLOSE_UNAUTHENTICATED)
        return
    conn = await ctx.hub.add_admin(admin_session_id, ws)
    try:
        await _receive_loop(ws, conn)
    finally:
        await ctx.hub.remove_admin(conn)


async def _receive_loop(ws: WebSocket, conn: Connection) -> None:
    """Only keepalive pings are accepted; anything else is ignored with an error reply."""
    try:
        while True:
            frame = await ws.receive()
            if frame["type"] == "websocket.disconnect":
                return
            message = _parse(frame.get("text"))
            if message is not None and message.get("type") == "ping":
                await conn.send({"type": "pong"})
            else:
                await conn.send({"type": "error", "message": "Unsupported message"})
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Raised when the socket was closed server-side while we were waiting.
        pass


def _parse(raw: str | None) -> dict | None:
    if raw is None or len(raw) > MAX_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    return message if isinstance(message, dict) else None
