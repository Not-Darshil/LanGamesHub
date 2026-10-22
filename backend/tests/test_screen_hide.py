"""Guest Screen Hide: server-authoritative, per-session, admin-only, survives reconnects."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CSRF_HEADER, CSRF_VALUE
from app.games import registry
from app.main import create_app
from tests.conftest import Browser, receive_until
from tests.relay_engine import RelayEngine


@pytest.fixture(autouse=True)
def relay_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.GAMES, "relay", RelayEngine())


def hide(admin: Browser, b: Browser, visibility: str = "HIDDEN"):  # noqa: ANN201
    return admin.put(f"/api/admin/players/{b.session_id}/screen", json={"visibility": visibility})


def assert_hidden_payload(payload: dict) -> None:
    assert payload["session"]["screen"] == "HIDDEN"
    assert set(payload) <= {"type", "session"}
    assert "nickname" not in payload["session"]


def test_hide_switches_only_the_selected_guest(admin: Browser,
                                               approved_player: Callable[[str], Browser]) -> None:
    target, bystander = approved_player("Target"), approved_player("Bystander")
    with target.ws("/ws/player") as t_ws, bystander.ws("/ws/player") as b_ws:
        assert t_ws.receive_json()["session"]["screen"] == "VISIBLE"
        b_ws.receive_json()
        response = hide(admin, target)
        assert response.json() == {"visibility": "HIDDEN", "changed": True}
        assert_hidden_payload(receive_until(t_ws, lambda m: m["session"]["screen"] == "HIDDEN"))
        b_ws.send_json({"type": "ping"})
        while (msg := b_ws.receive_json())["type"] != "pong":
            assert msg["session"]["screen"] == "VISIBLE"
    bystander_state = bystander.get("/api/state").json()
    assert bystander_state["session"]["screen"] == "VISIBLE" and "lobby" in bystander_state


def test_hidden_state_is_enforced_on_refresh_and_reconnect(
        admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Hidden")
    hide(admin, p)
    me = p.get("/api/me").json()
    assert me == {"id": p.session_id, "status": "APPROVED", "screen": "HIDDEN"}
    assert_hidden_payload(p.get("/api/state").json())
    for _ in range(2):
        with p.ws("/ws/player") as ws:
            assert_hidden_payload(ws.receive_json())


def test_hidden_state_survives_server_restart(app_settings, tmp_path,  # noqa: ANN001
                                              admin: Browser,
                                              approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Persistent")
    hide(admin, p)
    restarted = create_app(app_settings.model_copy(update={"frontend_dist_dir": tmp_path / "x"}))
    with TestClient(restarted, headers={CSRF_HEADER: CSRF_VALUE}) as client:
        b = Browser(client)
        b.cookies = dict(p.cookies)
        assert b.get("/api/me").json()["screen"] == "HIDDEN"
        with b.ws("/ws/player") as ws:
            assert_hidden_payload(ws.receive_json())


def test_restore_returns_full_interface(admin: Browser,
                                        approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Restored")
    hide(admin, p)
    with p.ws("/ws/player") as ws:
        assert_hidden_payload(ws.receive_json())
        assert hide(admin, p, "VISIBLE").json() == {"visibility": "VISIBLE", "changed": True}
        restored = receive_until(ws, lambda m: m["session"]["screen"] == "VISIBLE")
    assert restored["session"]["nickname"] == "Restored"
    assert "lobby" in restored


def test_hide_and_restore_are_idempotent(admin: Browser,
                                         approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Idem")
    assert hide(admin, p).json()["changed"] is True
    assert hide(admin, p).json() == {"visibility": "HIDDEN", "changed": False}
    assert hide(admin, p, "VISIBLE").json()["changed"] is True
    assert hide(admin, p, "VISIBLE").json() == {"visibility": "VISIBLE", "changed": False}


def test_guest_cannot_restore_own_screen(admin: Browser,
                                         approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Stuck")
    hide(admin, p)
    # Direct API call with the guest's own cookie.
    assert p.put(f"/api/admin/players/{p.session_id}/screen",
                 json={"visibility": "VISIBLE"}).status_code == 401
    # Forged WebSocket messages.
    with p.ws("/ws/player") as ws:
        ws.receive_json()
        ws.send_json({"type": "screen", "visibility": "VISIBLE"})
        assert ws.receive_json()["type"] == "error"
    assert p.get("/api/me").json()["screen"] == "HIDDEN"


def test_admin_dashboard_shows_screen_status(admin: Browser,
                                             approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Shown")
    hide(admin, p)
    entry = next(x for x in admin.get("/api/admin/state").json()["players"]
                 if x["id"] == p.session_id)
    assert entry["screen"] == "HIDDEN"
    assert entry["nickname"] == "Shown"  # the host still sees who it is


def test_only_active_approved_sessions_can_be_hidden(admin: Browser,
                                                     browser: Callable[[], Browser],
                                                     approved_player: Callable[[str], Browser]
                                                     ) -> None:
    pending = browser()
    response = pending.post("/api/access/request", json={"password": "letmein"})
    pending_id = response.json()["id"]
    assert admin.put(f"/api/admin/players/{pending_id}/screen",
                     json={"visibility": "HIDDEN"}).status_code == 409
    assert admin.put("/api/admin/players/9999/screen",
                     json={"visibility": "HIDDEN"}).status_code == 404
    p = approved_player("Valid")
    assert admin.put(f"/api/admin/players/{p.session_id}/screen",
                     json={"visibility": "BLURRED"}).status_code == 422


def test_hiding_does_not_change_game_state_or_turns(admin: Browser,
                                                    approved_player: Callable[[str], Browser]
                                                    ) -> None:
    a, b = approved_player("A"), approved_player("B")
    with ExitStack() as stack:
        for p in (a, b):
            stack.enter_context(p.ws("/ws/player")).receive_json()
        room_id = admin.post("/api/admin/rooms", json={"game_type": "relay", "name": "T",
                                                       "max_players": 2}).json()["id"]
        for p in (a, b):
            p.post(f"/api/rooms/{room_id}/join")
            p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
        admin.post(f"/api/admin/rooms/{room_id}/start")
        before = b.get("/api/state").json()["game"]

        hide(admin, a)
        after = b.get("/api/state").json()["game"]
        assert after["version"] == before["version"] and after["turn"] == str(a.session_id)
        # Rules and authorization still apply to the hidden player as normal.
        assert b.post(f"/api/rooms/{room_id}/actions",
                      json={"action": {"type": "pass"}}).json()["detail"] == "Not your turn"
        assert a.post(f"/api/rooms/{room_id}/actions",
                      json={"action": {"type": "pass"}}).status_code == 200
        hide(admin, a, "VISIBLE")
        state = a.get("/api/state").json()
        assert state["room"]["status"] == "IN_PROGRESS"
        assert state["game"]["turn"] == str(b.session_id)
        assert any(m["nickname"] == "A" for m in state["room"]["members"])
