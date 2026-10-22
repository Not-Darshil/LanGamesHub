"""Match history with placings and final positions; host sound controls."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack

import pytest

from app.games import registry
from tests.conftest import Browser, request_access
from tests.relay_engine import RelayEngine


@pytest.fixture(autouse=True)
def relay_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.GAMES, "relay", RelayEngine())


def play_relay(admin: Browser, players: list[Browser]) -> int:
    """Start a relay game with these players (all connected); returns the room id."""
    room_id = admin.post("/api/admin/rooms", json={
        "game_type": "relay", "name": "Relay", "max_players": len(players)}).json()["id"]
    for p in players:
        assert p.post(f"/api/rooms/{room_id}/join").status_code == 200
        p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 200
    return room_id


def test_history_standings_and_final_position(admin: Browser,
                                              approved_player: Callable[[str], Browser]) -> None:
    a, b, c, outsider = (approved_player(n) for n in ("Ann", "Ben", "Cat", "Out"))
    with ExitStack() as stack:
        for p in (a, b, c):
            stack.enter_context(p.ws("/ws/player")).receive_json()
        room_id = play_relay(admin, [a, b, c])
        assert c.post(f"/api/rooms/{room_id}/leave").status_code == 200  # Cat forfeits
        assert a.post(f"/api/rooms/{room_id}/actions",
                      json={"action": {"type": "claim"}}).status_code == 200

    result = a.get("/api/state").json()["room"]["result"]
    assert [(r["nickname"], r["place"], r["detail"]) for r in result["standings"]] == [
        ("Ann", 1, "Winner"), ("Ben", 2, ""), ("Cat", 3, "Left the game")]

    matches = b.get("/api/history").json()["matches"]
    assert len(matches) == 1
    match = matches[0]
    assert match["room_name"] == "Relay" and match["my_place"] == 2 and match["has_replay"]
    assert c.get("/api/history").json()["matches"][0]["my_place"] == 3  # leavers keep history
    assert outsider.get("/api/history").json()["matches"] == []

    # Each participant sees the final position from their own seat: their own secret only.
    detail_a = a.get(f"/api/history/{match['id']}").json()
    detail_b = b.get(f"/api/history/{match['id']}").json()
    assert detail_a["game"]["you"] == str(a.session_id)
    assert detail_a["game"]["my_secret"] is not None
    assert detail_a["game"]["my_secret"] != detail_b["game"]["my_secret"]
    assert detail_a["game"]["names"][str(b.session_id)] == "Ben"
    assert outsider.get(f"/api/history/{match['id']}").status_code == 404
    assert a.get("/api/history/999999").status_code == 404

    # The host gets the spectator view: no hidden information.
    host = admin.get(f"/api/admin/history/{match['id']}").json()
    assert host["game"]["my_secret"] is None and host["game"]["you"] == ""
    listed = admin.get("/api/admin/state").json()["history"][0]
    assert listed["standings"][0]["nickname"] == "Ann" and listed["has_replay"]


def test_hidden_guest_gets_no_history(admin: Browser,
                                      approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("Ann"), approved_player("Ben")
    with ExitStack() as stack:
        for p in (a, b):
            stack.enter_context(p.ws("/ws/player")).receive_json()
        room_id = play_relay(admin, [a, b])
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "claim"}})
    match_id = a.get("/api/history").json()["matches"][0]["id"]
    admin.put(f"/api/admin/players/{a.session_id}/screen", json={"visibility": "HIDDEN"})
    assert a.get("/api/history").json() == {"matches": []}
    response = a.get(f"/api/history/{match_id}")
    assert response.status_code == 404 and response.json()["detail"] == "Not available"


def test_sound_reporting_and_host_mutes(admin: Browser, browser: Callable[[], Browser],
                                        approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("Ann"), approved_player("Ben")

    def admin_player(p: Browser) -> dict:
        return next(x for x in admin.get("/api/admin/state").json()["players"]
                    if x["id"] == p.session_id)

    assert admin_player(a)["sound_enabled"] is None  # never reported
    assert a.put("/api/me/sound", json={"enabled": True}).status_code == 200
    b.put("/api/me/sound", json={"enabled": False})
    assert admin_player(a)["sound_enabled"] is True and admin_player(b)["sound_enabled"] is False

    # Mute one guest.
    assert admin.put(f"/api/admin/players/{a.session_id}/sound",
                     json={"muted": True}).json()["changed"] is True
    assert a.get("/api/state").json()["session"]["sound_muted"] is True
    assert b.get("/api/state").json()["session"]["sound_muted"] is False
    assert admin_player(a)["sound_muted_by_host"] is True

    # Mute everyone, including guests approved later; unmuting all keeps individual mutes.
    assert admin.put("/api/admin/sound", json={"muted": True}).status_code == 200
    late = approved_player("Late")
    assert all(p.get("/api/state").json()["session"]["sound_muted"] for p in (a, b, late))
    assert admin.get("/api/admin/state").json()["sound_muted_all"] is True
    admin.put("/api/admin/sound", json={"muted": False})
    assert a.get("/api/state").json()["session"]["sound_muted"] is True
    assert b.get("/api/state").json()["session"]["sound_muted"] is False

    # Only the admin can mute; only approved players can be muted.
    assert a.put("/api/admin/sound", json={"muted": False}).status_code == 401
    pending_id = request_access(browser())
    assert admin.put(f"/api/admin/players/{pending_id}/sound",
                     json={"muted": True}).status_code == 409
