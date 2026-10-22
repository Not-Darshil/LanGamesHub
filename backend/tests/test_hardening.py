"""Security headers, request limits, concurrency of game actions, and restart recovery."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import CSRF_HEADER, CSRF_VALUE
from app.main import create_app
from app.realtime.hub import CLOSE_TOO_MANY, MAX_CONNECTIONS_PER_SESSION
from app.services import rooms as room_service
from app.services.errors import ServiceError
from tests.conftest import Browser, expect_close, make_settings


def test_html_has_strict_csp_and_security_headers(dist_dir: Path) -> None:
    client = TestClient(create_app(make_settings(frontend_dist_dir=dist_dir)))
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "http:" not in csp and "https:" not in csp  # no remote origins allowed
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    api = client.get("/api/health")
    assert api.headers["cache-control"] == "no-store"


def test_oversized_request_bodies_are_rejected(browser: Callable[[], Browser]) -> None:
    b = browser()
    response = b.post("/api/access/request", json={"password": "x" * 70_000})
    assert response.status_code == 413


def test_socket_connections_per_session_are_capped(
        approved_player: Callable[[str], Browser]) -> None:
    p = approved_player("Tabs")
    with ExitStack() as stack:
        for _ in range(MAX_CONNECTIONS_PER_SESSION):
            stack.enter_context(p.ws("/ws/player")).receive_json()
        with p.ws("/ws/player") as extra:
            expect_close(extra, CLOSE_TOO_MANY)


def _uno_room(admin: Browser, a: Browser, b: Browser, stack: ExitStack) -> int:
    for p in (a, b):
        stack.enter_context(p.ws("/ws/player")).receive_json()
    room_id = admin.post("/api/admin/rooms", json={"game_type": "uno", "name": "U",
                                                   "max_players": 2}).json()["id"]
    for p in (a, b):
        p.post(f"/api/rooms/{room_id}/join")
        p.post(f"/api/rooms/{room_id}/ready", json={"ready": True})
    assert admin.post(f"/api/admin/rooms/{room_id}/start").status_code == 200
    return room_id


def test_concurrent_actions_are_serialized(client: TestClient, admin: Browser,
                                           approved_player: Callable[[str], Browser]) -> None:
    """The same intent sent many times at once is validated against fresh state each time."""
    a, b = approved_player("A"), approved_player("B")
    with ExitStack() as stack:
        room_id = _uno_room(admin, a, b, stack)
        state = a.get("/api/state").json()["game"]
        mover = a if state["current"] == str(a.session_id) else b
        start = mover.get("/api/state").json()["game"]
        before = start["version"]
        cards_before = sum(p["cards"] for p in start["players"])
        ctx = client.app.state.ctx
        barrier = threading.Barrier(8)
        outcomes: list[str] = []

        def draw() -> None:
            barrier.wait()
            try:
                ctx.transaction(lambda db: room_service.apply_action(
                    db, mover.session_id, room_id, {"type": "draw"}, ctx.rng))
                outcomes.append("ok")
            except ServiceError as exc:
                outcomes.append(exc.message)

        threads = [threading.Thread(target=draw) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        after = mover.get("/api/state").json()["game"]
        assert outcomes.count("ok") == 1, outcomes
        assert after["version"] == before + 1
        # Exactly one card was drawn (a Draw Two start card may already have dealt extras).
        assert sum(p["cards"] for p in after["players"]) == cards_before + 1


def test_running_game_survives_server_restart(app_settings, tmp_path: Path,  # noqa: ANN001
                                              admin: Browser,
                                              approved_player: Callable[[str], Browser]) -> None:
    a, b = approved_player("A"), approved_player("B")
    with ExitStack() as stack:
        room_id = _uno_room(admin, a, b, stack)
        before = a.get("/api/state").json()
    restarted = create_app(app_settings.model_copy(update={"frontend_dist_dir": tmp_path / "x"}))
    with TestClient(restarted, headers={CSRF_HEADER: CSRF_VALUE}) as client:
        a2, b2 = Browser(client), Browser(client)
        a2.cookies, b2.cookies = dict(a.cookies), dict(b.cookies)
        after = a2.get("/api/state").json()
        assert after["room"]["status"] == "IN_PROGRESS"
        assert after["game"]["hand"] == before["game"]["hand"]
        assert after["game"]["version"] == before["game"]["version"]
        # Play continues after the restart.
        mover = a2 if after["game"]["current"] == str(a.session_id) else b2
        response = mover.post(f"/api/rooms/{room_id}/actions", json={"action": {"type": "draw"}})
        assert response.status_code == 200
