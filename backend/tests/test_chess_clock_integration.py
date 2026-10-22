"""Room options through the API, and the server ending a game when a flag falls."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import ExitStack

import pytest

from app.games.registry import GAMES
from tests.conftest import Browser, receive_until


def test_room_options_are_validated_and_listed(admin: Browser,
                                               approved_player: Callable[[str], Browser]) -> None:
    bad = admin.post("/api/admin/rooms", json={
        "game_type": "chess", "name": "Bad", "options": {"time_control": "7+7"}})
    assert bad.status_code == 400 and "time control" in bad.json()["detail"]
    bad = admin.post("/api/admin/rooms", json={
        "game_type": "uno", "name": "Bad", "options": {"time_control": "1+0"}})
    assert bad.status_code == 400

    ok = admin.post("/api/admin/rooms", json={
        "game_type": "chess", "name": "Blitz", "options": {"time_control": "5+0"}})
    assert ok.status_code == 201
    p = approved_player("Pia")
    room = next(r for r in p.get("/api/state").json()["lobby"]["rooms"] if r["name"] == "Blitz")
    assert room["options"] == {"time_control": "5+0"}
    assert room["options_label"] == "5 min · Blitz"

    # Players can propose timed rooms too.
    proposed = p.post("/api/rooms", json={"game_type": "chess", "name": "Mine",
                                          "options": {"time_control": "1+0"}})
    assert proposed.status_code == 201
    assert p.get("/api/state").json()["room"]["options_label"] == "1 min · Bullet"


def test_server_ends_game_when_flag_falls(admin: Browser, monkeypatch: pytest.MonkeyPatch,
                                         approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("Alpha"), approved_player("Beta")
    with ExitStack() as stack:
        sockets = [stack.enter_context(p.ws("/ws/player")) for p in (a, b)]
        for ws in sockets:
            ws.receive_json()
        room_id = admin.post("/api/admin/rooms", json={
            "game_type": "chess", "name": "Bullet", "options": {"time_control": "1+0"},
        }).json()["id"]
        for p in (a, b):
            p.post(f"/api/rooms/{room_id}/join")
            p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
        assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 200

        game = a.get("/api/state").json()["game"]
        assert game["clock"]["label"] == "1 min · Bullet" and game["clock"]["running"] is None
        white = a if game["colors"][game["you"]] == "white" else b
        assert white.post(f"/api/rooms/{room_id}/actions",
                          json={"action": {"type": "move", "uci": "e2e4"}}).status_code == 200

        # Black never moves. Jump the server clock past Black's minute; the periodic
        # check must end the game without anyone acting.
        real = time.time
        monkeypatch.setattr(GAMES["chess"], "clock", lambda: real() + 120)
        message = receive_until(sockets[0], lambda m: (m.get("room") or {}).get("status")
                                == "COMPLETED", limit=200)
        result = message["room"]["result"]
        assert result["outcome"] == "WIN" and result["reason"] == "Timeout"
        assert result["winners"] == ["Alpha" if white is a else "Beta"]
        assert message["game"]["clock"]["remaining"]["black"] == 0
