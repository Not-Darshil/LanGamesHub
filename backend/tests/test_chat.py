"""Room chat and emoji reactions: membership, privacy, limits and the host switch."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.games import registry
from app.services import chat
from tests.conftest import Browser
from tests.relay_engine import RelayEngine


@pytest.fixture(autouse=True)
def relay_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.GAMES, "relay", RelayEngine())


def room_with(admin: Browser, *players: Browser) -> int:
    room_id = admin.post("/api/admin/rooms", json={
        "game_type": "relay", "name": "Talk", "max_players": 4}).json()["id"]
    for p in players:
        assert p.post(f"/api/rooms/{room_id}/join").status_code == 200
    return room_id


def chat_of(p: Browser) -> dict:
    return p.get("/api/state").json()["room"]["chat"]


def test_members_chat_and_react(admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a, b, outsider = approved_player("Ann"), approved_player("Ben"), approved_player("Out")
    room_id = room_with(admin, a, b)
    assert a.post(f"/api/rooms/{room_id}/chat", json={"text": "  good   luck \x07 all  "}).status_code == 201
    assert b.post(f"/api/rooms/{room_id}/react", json={"emoji": "🔥"}).status_code == 201

    for p in (a, b):
        room_chat = chat_of(p)
        assert [(m["nickname"], m["text"]) for m in room_chat["messages"]] == [("Ann", "good luck all")]
        assert room_chat["messages"][0]["from"] == str(a.session_id)
        assert [(r["nickname"], r["emoji"]) for r in room_chat["reactions"]] == [("Ben", "🔥")]
        assert p.get("/api/state").json()["room"]["chat_enabled"] is True

    # Not a member: cannot read (no room) or post.
    assert outsider.get("/api/state").json()["room"] is None
    assert outsider.post(f"/api/rooms/{room_id}/chat", json={"text": "hi"}).status_code == 403
    assert outsider.post(f"/api/rooms/{room_id}/react", json={"emoji": "👍"}).status_code == 403
    assert a.post("/api/rooms/999999/chat", json={"text": "hi"}).status_code == 404


def test_validation(admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a = approved_player("Ann")
    room_id = room_with(admin, a)
    assert a.post(f"/api/rooms/{room_id}/chat", json={"text": "   "}).status_code == 400
    assert a.post(f"/api/rooms/{room_id}/chat", json={"text": "x" * 301}).status_code == 400
    assert a.post(f"/api/rooms/{room_id}/react", json={"emoji": "💩"}).status_code == 400
    assert a.post(f"/api/rooms/{room_id}/chat", json={"text": "x" * 300}).status_code == 201


def test_rate_limits(admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a = approved_player("Ann")
    room_id = room_with(admin, a)
    codes = [a.post(f"/api/rooms/{room_id}/chat", json={"text": f"m{i}"}).status_code for i in range(7)]
    assert codes[:5] == [201] * 5 and codes[5:] == [429, 429]
    codes = [a.post(f"/api/rooms/{room_id}/react", json={"emoji": "👏"}).status_code for _ in range(10)]
    assert codes[:8] == [201] * 8 and codes[8:] == [429, 429]


def test_history_is_capped(admin: Browser, approved_player: Callable[[str], Browser],
                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "HISTORY", 3)
    monkeypatch.setattr(chat, "RECENT_REACTIONS", 2)
    a = approved_player("Ann")
    room_id = room_with(admin, a)
    for i in range(5):
        a.post(f"/api/rooms/{room_id}/chat", json={"text": f"m{i}"})
    for emoji in ("👍", "😂", "🎉"):
        a.post(f"/api/rooms/{room_id}/react", json={"emoji": emoji})
    room_chat = chat_of(a)
    assert [m["text"] for m in room_chat["messages"]] == ["m2", "m3", "m4"]  # oldest first
    assert [r["emoji"] for r in room_chat["reactions"]] == ["😂", "🎉"]


def test_host_can_turn_chat_off(admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a = approved_player("Ann")
    room_id = room_with(admin, a)
    a.post(f"/api/rooms/{room_id}/chat", json={"text": "before"})
    assert a.put("/api/admin/chat", json={"enabled": False}).status_code == 401
    assert admin.put("/api/admin/chat", json={"enabled": False}).status_code == 200
    assert admin.get("/api/admin/state").json()["chat_enabled"] is False
    room = a.get("/api/state").json()["room"]
    assert room["chat_enabled"] is False and room["chat"] == {"messages": [], "reactions": []}
    response = a.post(f"/api/rooms/{room_id}/chat", json={"text": "after"})
    assert response.status_code == 409 and "turned chat off" in response.json()["detail"]
    admin.put("/api/admin/chat", json={"enabled": True})
    assert [m["text"] for m in chat_of(a)["messages"]] == ["before"]


def test_hidden_guest_gets_masked_errors(admin: Browser,
                                         approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("Ann"), approved_player("Ben")
    room_id = room_with(admin, a, b)
    b.post(f"/api/rooms/{room_id}/chat", json={"text": "secret plan"})
    admin.put(f"/api/admin/players/{a.session_id}/screen", json={"visibility": "HIDDEN"})
    assert "room" not in a.get("/api/state").json()
    response = a.post("/api/rooms/999999/chat", json={"text": "hi"})
    assert response.json()["detail"] == "Not available"


def test_chat_goes_with_the_room(admin: Browser, approved_player: Callable[[str], Browser]) -> None:
    a = approved_player("Ann")
    room_id = room_with(admin, a)
    a.post(f"/api/rooms/{room_id}/chat", json={"text": "bye"})
    assert admin.delete(f"/api/admin/rooms/{room_id}").status_code == 200
    a.post("/api/rooms", json={"game_type": "relay", "name": "New"})
    assert chat_of(a)["messages"] == []
