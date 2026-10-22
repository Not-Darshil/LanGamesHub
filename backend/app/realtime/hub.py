"""WebSocket connection registry and state pusher.

Clients never receive deltas. Whenever anything changes, the hub rebuilds the full view
each connected client is authorized to see and sends it (skipping unchanged views).
This makes reconnects trivial and means authorization is re-evaluated on every push:
a session that is no longer authorized is disconnected instead of being sent data.

Client-to-server WebSocket messages are limited to keepalive pings; every state change
goes through authenticated REST endpoints.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi.concurrency import run_in_threadpool
from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)

# WebSocket close codes understood by the frontend.
CLOSE_UNAUTHENTICATED = 4401  # no session, or it expired: start over
CLOSE_FORBIDDEN = 4403        # rejected or revoked: blank screen
CLOSE_KICKED = 4000           # disconnected by the host: may reconnect manually

CLOSE_TOO_MANY = 4429        # this session already has the maximum number of sockets
MAX_CONNECTIONS_PER_SESSION = 5
SEND_TIMEOUT_SECONDS = 5
PERIODIC_REFRESH_SECONDS = 30  # enforces expirations even when nothing else changes


@dataclass
class PlayerPush:
    """Result of evaluating one player session: a view to send, or a close code."""

    view: dict[str, Any] | None = None
    close_code: int | None = None


@dataclass
class Snapshot:
    players: dict[int, PlayerPush]
    admin_view: dict[str, Any] | None
    valid_admin_sessions: set[int]


SnapshotBuilder = Callable[[set[int], set[int]], Snapshot]  # (online players, admin sessions)
OfflineCallback = Callable[[int], Awaitable[None]]


@dataclass(eq=False)
class Connection:
    ws: WebSocket
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_sent: str | None = None

    async def send(self, payload: dict[str, Any], *, dedupe: bool = False) -> bool:
        text = json.dumps(payload, separators=(",", ":"), default=str)
        async with self.send_lock:
            if dedupe and text == self.last_sent:
                return True
            if self.ws.client_state != WebSocketState.CONNECTED:
                return False
            try:
                await asyncio.wait_for(self.ws.send_text(text), SEND_TIMEOUT_SECONDS)
            except Exception:
                return False
            if dedupe:
                self.last_sent = text
            return True

    async def close(self, code: int) -> None:
        async with self.send_lock:
            if self.ws.client_state == WebSocketState.CONNECTED:
                with contextlib.suppress(Exception):
                    await self.ws.close(code=code)


class Hub:
    def __init__(self, builder: SnapshotBuilder, grace_seconds: float = 0) -> None:
        self._builder = builder
        self._grace_seconds = grace_seconds
        self.players: dict[int, set[Connection]] = defaultdict(set)
        self.admins: dict[Connection, int] = {}
        self._dirty = asyncio.Event()
        self._push_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._grace_tasks: dict[int, asyncio.Task[None]] = {}
        self.offline_callbacks: list[OfflineCallback] = []

    # -- lifecycle -------------------------------------------------------------------

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._push_loop(), name="hub-push"),
            asyncio.create_task(self._refresh_loop(), name="hub-refresh"),
        ]

    async def stop(self) -> None:
        for task in [*self._tasks, *self._grace_tasks.values()]:
            task.cancel()
        for task in [*self._tasks, *self._grace_tasks.values()]:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
        self._grace_tasks.clear()

    def notify(self) -> None:
        """Schedule a push of fresh state to every client. Bursts are coalesced."""
        self._dirty.set()

    async def flush(self) -> None:
        """Push immediately and wait for completion (used where ordering matters)."""
        self._dirty.clear()
        await self._push_all()

    # -- registration ----------------------------------------------------------------

    def online_ids(self) -> set[int]:
        return {sid for sid, conns in self.players.items() if conns}

    def is_online(self, session_id: int) -> bool:
        return bool(self.players.get(session_id))

    def has_capacity(self, session_id: int) -> bool:
        return len(self.players.get(session_id, ())) < MAX_CONNECTIONS_PER_SESSION

    async def add_player(self, session_id: int, ws: WebSocket) -> Connection:
        conn = Connection(ws)
        grace = self._grace_tasks.pop(session_id, None)
        if grace is not None:
            grace.cancel()
        self.players[session_id].add(conn)
        try:
            await self.flush()
        except BaseException:
            await self.remove_player(session_id, conn)
            raise
        return conn

    async def remove_player(self, session_id: int, conn: Connection) -> None:
        conns = self.players.get(session_id)
        if conns is not None:
            conns.discard(conn)
            if not conns:
                del self.players[session_id]
                self._schedule_offline(session_id)
        self.notify()

    async def add_admin(self, admin_session_id: int, ws: WebSocket) -> Connection:
        conn = Connection(ws)
        self.admins[conn] = admin_session_id
        try:
            await self.flush()
        except BaseException:
            await self.remove_admin(conn)
            raise
        return conn

    async def remove_admin(self, conn: Connection) -> None:
        self.admins.pop(conn, None)

    async def close_player(self, session_id: int, code: int) -> None:
        for conn in list(self.players.get(session_id, ())):
            await conn.close(code)

    # -- pushing ---------------------------------------------------------------------

    async def _push_loop(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self._push_all()
            except Exception:
                logger.exception("State push failed")
                await asyncio.sleep(1)

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(PERIODIC_REFRESH_SECONDS)
            self.notify()

    async def _push_all(self) -> None:
        async with self._push_lock:
            # Only push to connections that existed when the snapshot was taken; one that
            # registers while it is being built gets its own push via add_* -> flush().
            player_conns = {sid: set(conns) for sid, conns in self.players.items() if conns}
            admin_conns = dict(self.admins)
            snapshot = await run_in_threadpool(self._builder, set(player_conns),
                                               set(admin_conns.values()))
            sends: list[Awaitable[Any]] = []
            for sid, conns in player_conns.items():
                push = snapshot.players.get(sid) or PlayerPush(close_code=CLOSE_UNAUTHENTICATED)
                for conn in conns:
                    if push.close_code is not None:
                        sends.append(conn.close(push.close_code))
                    else:
                        sends.append(conn.send({"type": "state", **(push.view or {})}, dedupe=True))
            for conn, admin_sid in admin_conns.items():
                if admin_sid not in snapshot.valid_admin_sessions or snapshot.admin_view is None:
                    sends.append(conn.close(CLOSE_UNAUTHENTICATED))
                else:
                    sends.append(conn.send({"type": "admin_state", **snapshot.admin_view},
                                           dedupe=True))
            await asyncio.gather(*sends)

    # -- disconnect grace ------------------------------------------------------------

    def _schedule_offline(self, session_id: int) -> None:
        if not self.offline_callbacks:
            return
        previous = self._grace_tasks.pop(session_id, None)
        if previous is not None:
            previous.cancel()
        self._grace_tasks[session_id] = asyncio.create_task(self._offline_after_grace(session_id))

    async def _offline_after_grace(self, session_id: int) -> None:
        await asyncio.sleep(self._grace_seconds)
        self._grace_tasks.pop(session_id, None)
        if self.is_online(session_id):
            return
        for callback in self.offline_callbacks:
            try:
                await callback(session_id)
            except Exception:
                logger.exception("Offline handler failed for session %s", session_id)
