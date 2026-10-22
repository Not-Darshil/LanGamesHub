"""Room state machine, host start approval, membership rules, isolation, and races."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.games import registry
from app.services import rooms as room_service
from app.services.errors import ServiceError
from tests.conftest import Browser, receive_until
from tests.relay_engine import RelayEngine


@pytest.fixture(autouse=True)
def relay_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(registry.GAMES, "relay", RelayEngine())


def create_room(admin: Browser, max_players: int = 2, name: str = "Table") -> int:
    response = admin.post("/api/admin/rooms",
                          json={"game_type": "relay", "name": name, "max_players": max_players})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def room_of(b: Browser) -> dict | None:
    return b.get("/api/state").json()["room"]


def admin_room(admin: Browser, room_id: int) -> dict:
    return next(r for r in admin.get("/api/admin/state").json()["rooms"] if r["id"] == room_id)


@pytest.fixture
def connected() -> Iterator[Callable[..., None]]:
    """Open player WebSockets for the duration of a test (start requires them online)."""
    with ExitStack() as stack:
        def connect(*browsers: Browser) -> None:
            for b in browsers:
                ws = stack.enter_context(b.ws("/ws/player"))
                ws.receive_json()
        yield connect


def ready_room(admin: Browser, *players: Browser, max_players: int = 2) -> int:
    room_id = create_room(admin, max_players=max_players)
    for p in players:
        assert p.post(f"/api/rooms/{room_id}/join").status_code == 200
        p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    return room_id


def test_admin_room_is_open_and_listed(admin: Browser,
                                       approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Ann")
    room_id = create_room(admin, name="  Friday   Night ")
    lobby = p.get("/api/state").json()["lobby"]
    room = next(r for r in lobby["rooms"] if r["id"] == room_id)
    assert room["name"] == "Friday Night"
    assert room["status"] == "WAITING_FOR_PLAYERS"
    assert room["creator"] == "host (admin)"
    info = admin_room(admin, room_id)
    assert info["approved"] is True and info["max_players"] == 2


def test_room_config_is_validated(admin: Browser) -> None:
    bad = [{"game_type": "nope", "name": "x"},
           {"game_type": "relay", "name": "x", "max_players": 5},
           {"game_type": "relay", "name": "x", "max_players": 1},
           {"game_type": "relay", "name": "   "}]
    for body in bad:
        assert admin.post("/api/admin/rooms", json=body).status_code == 400, body


def test_player_proposal_needs_host_approval(admin: Browser,
                                            approved_player: Callable[[str], Browser]) -> None:
    proposer, other = approved_player("Prop"), approved_player("Other")
    response = proposer.post("/api/rooms", json={"game_type": "relay", "name": "Mine"})
    assert response.status_code == 201
    room_id = response.json()["id"]
    assert room_of(proposer)["status"] == "CREATED"
    # Not listed for, or joinable by, anyone else until approved.
    assert all(r["id"] != room_id for r in other.get("/api/state").json()["lobby"]["rooms"])
    assert other.post(f"/api/rooms/{room_id}/join").status_code == 409
    proposer.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 409
    assert admin.post(f"/api/admin/rooms/{room_id}/approve").json()["status"] == \
        "WAITING_FOR_PLAYERS"
    assert other.post(f"/api/rooms/{room_id}/join").status_code == 200
    assert admin_room(admin, room_id)["creator"] == "Prop"


def test_full_and_ready_room_does_not_start_itself(
        admin: Browser, approved_player: Callable[[str], Browser],
        connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a, b)
    room_id = create_room(admin)
    a.post(f"/api/rooms/{room_id}/join")
    a.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert room_of(a)["status"] == "WAITING_FOR_PLAYERS"  # below minimum players
    b.post(f"/api/rooms/{room_id}/join")
    assert room_of(a)["status"] == "WAITING_FOR_PLAYERS"  # b is not ready
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 409
    b.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert room_of(a)["status"] == "READY_TO_START"
    assert room_of(a)["status"] == "READY_TO_START"  # still waiting on the host
    assert room_of(a)["members"][0]["is_ready"] is True
    assert b.get("/api/state").json()["game"] is None

    assert a.post(f"/api/admin/rooms/{room_id}/start").status_code == 401  # players can't
    assert admin.post(f"/api/admin/rooms/{room_id}/start").json()["status"] == "IN_PROGRESS"
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 409
    state = a.get("/api/state").json()
    assert state["room"]["status"] == "IN_PROGRESS"
    assert state["game"]["turn"] == str(a.session_id)
    assert state["game"]["names"] == {str(a.session_id): "A", str(b.session_id): "B"}


def test_unready_after_ready_returns_to_waiting(admin: Browser,
                                                approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("A"), approved_player("B")
    room_id = ready_room(admin, a, b)
    assert room_of(a)["status"] == "READY_TO_START"
    b.post(f"/api/rooms/{room_id}/ready", json={"ready": False})
    assert room_of(a)["status"] == "WAITING_FOR_PLAYERS"
    b.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    b.post(f"/api/rooms/{room_id}/leave")
    assert room_of(a)["status"] == "WAITING_FOR_PLAYERS"


def test_start_requires_everyone_connected(admin: Browser,
                                           approved_player: Callable[[str], Browser],
                                           connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("Offline")
    connected(a)
    room_id = ready_room(admin, a, b)
    response = admin.post(f"/api/admin/rooms/{room_id}/start")
    assert response.status_code == 409
    assert "Offline" in response.json()["detail"]


def test_capacity_lock_and_single_room_rules(admin: Browser,
                                            approved_player: Callable[[str], Browser]) -> None:
    a, b, c = approved_player("A"), approved_player("B"), approved_player("C")
    room_id = create_room(admin, max_players=2)
    other_room = create_room(admin, name="Other")
    a.post(f"/api/rooms/{room_id}/join")
    assert a.post(f"/api/rooms/{other_room}/join").status_code == 409  # one room at a time
    b.post(f"/api/rooms/{room_id}/join")
    assert c.post(f"/api/rooms/{room_id}/join").json()["detail"] == "This room is full"
    assert admin.post(f"/api/admin/rooms/{room_id}/lock").status_code == 200
    assert b.post(f"/api/rooms/{room_id}/leave").json()["detail"] == "This room is locked"
    admin.post(f"/api/admin/rooms/{room_id}/unlock")
    assert b.post(f"/api/rooms/{room_id}/leave").status_code == 200
    admin.post(f"/api/admin/rooms/{room_id}/lock")
    assert c.post(f"/api/rooms/{room_id}/join").json()["detail"] == "This room is locked"


def test_room_details_and_game_state_are_isolated(
        admin: Browser, approved_player: Callable[[str], Browser],
        connected: Callable[..., None]) -> None:
    a, b, outsider = approved_player("A"), approved_player("B"), approved_player("Out")
    connected(a, b, outsider)
    room_id = ready_room(admin, a, b)
    admin.post(f"/api/admin/rooms/{room_id}/start")

    out_state = outsider.get("/api/state").json()
    assert out_state["room"] is None and out_state["game"] is None
    summary = next(r for r in out_state["lobby"]["rooms"] if r["id"] == room_id)
    assert "members" not in summary  # lobby only shows counts
    assert outsider.post(f"/api/rooms/{room_id}/actions",
                         json={"action": {"type": "claim"}}).status_code == 403

    a_secret = a.get("/api/state").json()["game"]["my_secret"]
    b_view = b.get("/api/state").json()
    assert b_view["game"]["my_secret"] != a_secret
    assert str(a_secret) not in str(b_view)
    # The admin dashboard never carries game state (the host may be a player).
    assert str(a_secret) not in admin.get("/api/admin/state").text


def test_pushes_only_reach_room_members(admin: Browser,
                                        approved_player: Callable[[str], Browser],
                                        connected: Callable[..., None]) -> None:
    a, b, outsider = approved_player("A"), approved_player("B"), approved_player("Out")
    connected(a, b)
    room_id = ready_room(admin, a, b)
    admin.post(f"/api/admin/rooms/{room_id}/start")
    with outsider.ws("/ws/player") as ws:
        receive_until(ws, lambda m: "lobby" in m)
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "pass"}})
        a.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "pass"}})
        ws.send_json({"type": "ping"})
        seen = []
        while (msg := ws.receive_json())["type"] != "pong":
            seen.append(msg)
        assert all(m.get("game") is None and m.get("room") is None for m in seen)


def test_actions_are_validated_by_engine(admin: Browser,
                                         approved_player: Callable[[str], Browser],
                                         connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a, b)
    room_id = ready_room(admin, a, b)
    assert a.post(f"/api/rooms/{room_id}/actions",
                  json={"action": {"type": "pass"}}).status_code == 409  # not started
    admin.post(f"/api/admin/rooms/{room_id}/start")
    assert b.post(f"/api/rooms/{room_id}/actions",
                  json={"action": {"type": "pass"}}).json()["detail"] == "Not your turn"
    assert a.post(f"/api/rooms/{room_id}/actions",
                  json={"action": {"nope": 1}}).json()["detail"] == "Malformed action"
    version = a.get("/api/state").json()["game"]["version"]
    assert a.post(f"/api/rooms/{room_id}/actions",
                  json={"action": {"type": "claim"}}).json()["status"] == "COMPLETED"
    state = b.get("/api/state").json()
    assert state["game"]["version"] == version + 1
    assert state["room"]["result"] == {
        "outcome": "WIN", "winners": ["A"], "reason": "claimed",
        "standings": [{"id": str(a.session_id), "nickname": "A", "place": 1, "detail": "Winner"},
                      {"id": str(b.session_id), "nickname": "B", "place": 2, "detail": ""}]}
    assert a.post(f"/api/rooms/{room_id}/actions",
                  json={"action": {"type": "pass"}}).status_code == 409
    history = admin.get("/api/admin/state").json()["history"]
    assert history[0]["winners"] == ["A"] and history[0]["participants"] == ["A", "B"]


def test_leaving_mid_game_forfeits(admin: Browser, approved_player: Callable[[str], Browser],
                                   connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a, b)
    room_id = ready_room(admin, a, b)
    admin.post(f"/api/admin/rooms/{room_id}/start")
    assert a.post(f"/api/rooms/{room_id}/leave").json()["status"] == "COMPLETED"
    assert room_of(b)["result"]["winners"] == ["B"]
    assert room_of(a) is None
    # B can move on to another room, leaving the finished one automatically.
    new_room = create_room(admin, name="Next")
    assert b.post(f"/api/rooms/{new_room}/join").status_code == 200
    assert room_of(b)["id"] == new_room


def test_revocation_vacates_seat_and_can_end_game(
        admin: Browser, approved_player: Callable[[str], Browser],
        connected: Callable[..., None]) -> None:
    a, b, c = approved_player("A"), approved_player("B"), approved_player("C")
    waiting = create_room(admin, max_players=2, name="Waiting")
    c.post(f"/api/rooms/{waiting}/join")
    admin.post(f"/api/admin/rooms/{waiting}/lock")
    admin.post(f"/api/admin/players/{c.session_id}/revoke")
    assert admin_room(admin, waiting)["members"] == []

    connected(a, b)
    room_id = ready_room(admin, a, b)
    admin.post(f"/api/admin/rooms/{room_id}/start")
    admin.post(f"/api/admin/players/{a.session_id}/revoke")
    room = room_of(b)
    assert room["status"] == "COMPLETED" and room["result"]["winners"] == ["B"]


def test_host_finish_cancel_and_remove(admin: Browser, approved_player: Callable[[str], Browser],
                                       connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a, b)
    room_id = ready_room(admin, a, b)
    assert admin.post(f"/api/admin/rooms/{room_id}/finish").status_code == 409  # not started
    admin.post(f"/api/admin/rooms/{room_id}/start")
    assert admin.post(f"/api/admin/rooms/{room_id}/finish").json()["status"] == "COMPLETED"
    assert room_of(a)["result"]["outcome"] == "ABORTED"

    other = create_room(admin, name="Doomed")
    assert admin.post(f"/api/admin/rooms/{other}/cancel").json()["status"] == "CANCELLED"
    assert admin.delete(f"/api/admin/rooms/{other}").status_code == 200
    assert all(r["id"] != other for r in admin.get("/api/admin/state").json()["rooms"])
    assert admin.delete(f"/api/admin/rooms/{other}").status_code == 404
    # History survives removing the room it came from.
    assert admin.delete(f"/api/admin/rooms/{room_id}").status_code == 200
    assert admin.get("/api/admin/state").json()["history"][0]["outcome"] == "ABORTED"


def test_disconnected_member_loses_ready_after_grace(
        admin: Browser, approved_player: Callable[[str], Browser],
        connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a)
    room_id = ready_room(admin, a, b)
    assert room_of(a)["status"] == "READY_TO_START"
    with a.ws("/ws/player") as ws:
        receive_until(ws, lambda m: m.get("room") is not None)
        with b.ws("/ws/player") as b_ws:
            b_ws.receive_json()
        # Grace period is 0 in tests: B's ready flag drops, room goes back to waiting.
        msg = receive_until(ws, lambda m: m["room"]["status"] == "WAITING_FOR_PLAYERS")
    member_b = next(m for m in msg["room"]["members"] if m["nickname"] == "B")
    assert member_b["is_ready"] is False and member_b["online"] is False


def test_disconnect_does_not_alter_running_game(admin: Browser,
                                                approved_player: Callable[[str], Browser],
                                                connected: Callable[..., None]) -> None:
    a, b = approved_player("A"), approved_player("B")
    connected(a)
    with b.ws("/ws/player") as b_ws:
        b_ws.receive_json()
        room_id = ready_room(admin, a, b)
        admin.post(f"/api/admin/rooms/{room_id}/start")
    with a.ws("/ws/player") as ws:
        msg = receive_until(ws, lambda m: m.get("room") is not None and any(
            x["nickname"] == "B" and not x["online"] for x in m["room"]["members"]))
    assert msg["room"]["status"] == "IN_PROGRESS"
    # B reconnects and resumes with their own private view.
    with b.ws("/ws/player") as b_ws:
        state = b_ws.receive_json()
    assert state["game"]["players"] == [str(a.session_id), str(b.session_id)]
    assert state["game"]["my_secret"] is not None


def test_host_can_join_as_regular_participant(admin: Browser,
                                              approved_player: Callable[[str], Browser],
                                              connected: Callable[..., None]) -> None:
    admin.post("/api/admin/host-player", json={"nickname": "Host"})
    guest = approved_player("Guest")
    connected(admin, guest)
    room_id = ready_room(admin, admin, guest)
    admin.post(f"/api/admin/rooms/{room_id}/start")
    state = admin.get("/api/state").json()
    members = state["room"]["members"]
    assert [m["is_host"] for m in members] == [True, False]
    assert admin.post(f"/api/rooms/{room_id}/actions",
                      json={"action": {"type": "claim"}}).json()["status"] == "COMPLETED"


def test_concurrent_joins_never_overfill(client: TestClient, admin: Browser,
                                         approved_player: Callable[[str], Browser]) -> None:
    room_id = create_room(admin, max_players=2)
    contenders = [approved_player(f"P{i}") for i in range(6)]
    ctx = client.app.state.ctx
    barrier = threading.Barrier(len(contenders))
    results: list[str] = []

    def join(p: Browser) -> None:
        barrier.wait()
        try:
            ctx.transaction(lambda db: room_service.join_room(db, p.session_id, room_id))
            results.append("ok")
        except ServiceError as exc:
            results.append(exc.message)

    threads = [threading.Thread(target=join, args=(p,)) for p in contenders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 2
    assert results.count("This room is full") == 4
    assert len(admin_room(admin, room_id)["members"]) == 2


def test_concurrent_starts_start_once(client: TestClient, admin: Browser,
                                      approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("A"), approved_player("B")
    room_id = ready_room(admin, a, b)
    ctx = client.app.state.ctx
    online = {a.session_id, b.session_id}
    barrier = threading.Barrier(5)
    results: list[str] = []

    def start() -> None:
        barrier.wait()
        try:
            ctx.transaction(lambda db: room_service.start_room(db, room_id, online, ctx.rng))
            results.append("ok")
        except ServiceError as exc:
            results.append(exc.message)

    threads = [threading.Thread(target=start) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert results.count("The game has already started") == 4
