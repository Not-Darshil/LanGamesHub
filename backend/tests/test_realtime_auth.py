"""WebSocket authentication, live notifications, and server-side disconnection."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from starlette.websockets import WebSocketDisconnect

from app.realtime.hub import CLOSE_FORBIDDEN, CLOSE_KICKED, CLOSE_UNAUTHENTICATED
from tests.conftest import Browser, expect_close, receive_until, request_access


def test_player_socket_requires_session(browser: Callable[[], Browser]) -> None:
    with browser().ws("/ws/player") as ws:
        expect_close(ws, CLOSE_UNAUTHENTICATED)


def test_admin_socket_requires_admin(approved_player: Callable[[str], Browser]) -> None:
    with approved_player("P").ws("/ws/admin") as ws:
        expect_close(ws, CLOSE_UNAUTHENTICATED)


def test_socket_rejects_foreign_origin(approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("P")
    with pytest.raises(WebSocketDisconnect), p.ws("/ws/player",
                                                  headers={"origin": "http://evil.example"}):
        pass


def test_pending_guest_is_notified_of_approval(browser: Callable[[], Browser],
                                               admin: Browser) -> None:
    b = browser()
    sid = request_access(b)
    with b.ws("/ws/player") as ws:
        first = ws.receive_json()
        assert first["type"] == "state"
        assert first["session"]["status"] == "PENDING"
        assert set(first) == {"type", "session"}  # pending guests see nothing else
        admin.post(f"/api/admin/players/{sid}/approve")
        receive_until(ws, lambda m: m["session"]["status"] == "APPROVED")


def test_host_receives_live_access_requests(browser: Callable[[], Browser],
                                            admin: Browser) -> None:
    with admin.ws("/ws/admin") as ws:
        assert ws.receive_json()["pending"] == []
        sid = request_access(browser())
        message = receive_until(ws, lambda m: m.get("pending"))
        assert message["type"] == "admin_state"
        assert message["pending"][0]["id"] == sid


def test_rejection_closes_waiting_guest_socket(browser: Callable[[], Browser],
                                               admin: Browser) -> None:
    b = browser()
    sid = request_access(b)
    with b.ws("/ws/player") as ws:
        ws.receive_json()
        admin.post(f"/api/admin/players/{sid}/reject")
        expect_close(ws, CLOSE_FORBIDDEN)
    # Reconnecting does not help.
    with b.ws("/ws/player") as ws:
        expect_close(ws, CLOSE_FORBIDDEN)


def test_revocation_closes_live_socket(approved_player: Callable[[str], Browser],
                                       admin: Browser) -> None:
    p = approved_player("Revokee")
    with p.ws("/ws/player") as ws:
        ws.receive_json()
        admin.post(f"/api/admin/players/{p.session_id}/revoke")
        expect_close(ws, CLOSE_FORBIDDEN)


def test_disconnect_kicks_but_keeps_session(approved_player: Callable[[str], Browser],
                                            admin: Browser) -> None:
    p = approved_player("Kicked")
    with p.ws("/ws/player") as ws:
        ws.receive_json()
        admin.post(f"/api/admin/players/{p.session_id}/disconnect")
        expect_close(ws, CLOSE_KICKED)
    assert p.get("/api/me").status_code == 200
    with p.ws("/ws/player") as ws:
        assert ws.receive_json()["session"]["status"] == "APPROVED"


def test_admin_sees_connection_status(approved_player: Callable[[str], Browser],
                                      admin: Browser) -> None:
    p = approved_player("Online")
    with admin.ws("/ws/admin") as admin_ws:
        admin_ws.receive_json()
        with p.ws("/ws/player") as ws:
            ws.receive_json()
            receive_until(admin_ws, lambda m: any(
                x["id"] == p.session_id and x["online"] for x in m["players"]))
        receive_until(admin_ws, lambda m: any(
            x["id"] == p.session_id and not x["online"] for x in m["players"]))


def test_admin_logout_closes_admin_socket(admin: Browser) -> None:
    with admin.ws("/ws/admin") as ws:
        ws.receive_json()
        admin.post("/api/admin/logout")
        expect_close(ws, CLOSE_UNAUTHENTICATED)


def test_client_messages_cannot_change_state(approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Forger")
    with p.ws("/ws/player") as ws:
        ws.receive_json()
        for forged in ({"type": "approve", "session_id": p.session_id},
                       {"type": "state", "session": {"status": "APPROVED"}}, "garbage"):
            if isinstance(forged, dict):
                ws.send_json(forged)
            else:
                ws.send_text(forged)
            assert ws.receive_json() == {"type": "error", "message": "Unsupported message"}
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
