"""Regressions for issues found in code review."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack

import pytest

from app.games import registry
from tests.conftest import Browser, receive_until, request_access
from tests.relay_engine import RelayEngine


def _start(admin: Browser, players: list[Browser], game_type: str, stack: ExitStack) -> tuple[int, list]:
    sockets = [stack.enter_context(p.ws("/ws/player")) for p in players]
    for ws in sockets:
        ws.receive_json()
    room_id = admin.post("/api/admin/rooms", json={"game_type": game_type, "name": "R",
                                                   "max_players": len(players)}).json()["id"]
    for p in players:
        p.post(f"/api/rooms/{room_id}/join")
        p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 200
    return room_id, sockets


def test_seat_zero_leaving_after_moving_keeps_pushes_alive(
        admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("A"), approved_player("B")
    with ExitStack() as stack:
        room_id, sockets = _start(admin, [a, b], "snakes", stack)
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "roll"}})
        a.post(f"/api/rooms/{room_id}/leave")
        state = b.get("/api/state")
        assert state.status_code == 200
        assert state.json()["room"]["result"]["winners"] == ["B"]
        pushed = receive_until(sockets[1], lambda m: (m.get("room") or {}).get("status")
                               == "COMPLETED")
        assert pushed["game"]["winner"] == str(b.session_id)


def test_one_broken_view_does_not_stop_other_pushes(
        admin: Browser, approved_player: Callable[[str], Browser],
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.GAMES, "relay", RelayEngine())
    a, b = approved_player("A"), approved_player("B")
    original = RelayEngine.view

    def flaky(self, state, player):  # noqa: ANN001, ANN202
        if player == str(a.session_id):
            raise RuntimeError("boom")
        return original(self, state, player)

    with ExitStack() as stack:
        room_id, sockets = _start(admin, [a, b], "relay", stack)
        monkeypatch.setattr(RelayEngine, "view", flaky)
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "pass"}})
        b_msg = receive_until(sockets[1], lambda m: (m.get("game") or {}).get("turn")
                              == str(b.session_id))
        assert b_msg["game"]["my_secret"] is not None
        a_msg = receive_until(sockets[0], lambda m: "lobby" not in m)
        assert set(a_msg) == {"type", "session"}


def test_failed_initial_push_unregisters_connection(
        client, approved_player: Callable[[str], Browser],  # noqa: ANN001
        monkeypatch: pytest.MonkeyPatch) -> None:
    p = approved_player("Ghost")
    hub = client.app.state.ctx.hub

    async def broken_flush() -> None:
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(hub, "flush", broken_flush)
    with pytest.raises(Exception), p.ws("/ws/player") as ws:  # noqa: B017
        ws.receive_json()
    assert not hub.is_online(p.session_id)


def test_proposing_a_room_requires_a_nickname(browser: Callable[[], Browser],
                                              admin: Browser) -> None:
    b = browser()
    admin.post(f"/api/admin/players/{request_access(b)}/approve")
    response = b.post("/api/rooms", json={"game_type": "uno", "name": "Mine"})
    assert response.status_code == 400 and response.json()["detail"] == "Choose a nickname first"


def test_hidden_guest_errors_reveal_nothing(admin: Browser,
                                            approved_player: Callable[[str], Browser]) -> None:
    taken, hidden = approved_player("Taken"), approved_player("Hidden")
    room_id = admin.post("/api/admin/rooms", json={"game_type": "uno", "name": "Secret Room",
                                                   "max_players": 2}).json()["id"]
    admin.post(f"/api/admin/rooms/{room_id}/lock")
    admin.put(f"/api/admin/players/{hidden.session_id}/screen", json={"visibility": "HIDDEN"})
    response = hidden.post(f"/api/rooms/{room_id}/join")
    assert response.status_code == 409 and response.json() == {"detail": "Not available"}
    # The same call from a visible guest still explains itself.
    assert taken.post(f"/api/rooms/{room_id}/join").json()["detail"] == "This room is locked"
