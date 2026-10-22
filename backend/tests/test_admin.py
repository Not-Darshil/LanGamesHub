"""Admin authentication, dashboard data, host player identity, and CSRF protection."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.ratelimit import RateLimiter
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, Browser, request_access


def test_admin_login_and_logout(browser: Callable[[], Browser]) -> None:
    b = browser()
    assert b.get("/api/admin/me").status_code == 401
    bad = b.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": "wrong"})
    assert bad.status_code == 401
    good = b.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert good.status_code == 200
    assert b.get("/api/admin/me").json() == {"username": ADMIN_USERNAME}
    token = b.cookies["lgh_admin"]
    assert b.post("/api/admin/logout").status_code == 200
    # The old token is dead server-side, not just removed from the browser.
    b.cookies["lgh_admin"] = token
    assert b.get("/api/admin/me").status_code == 401


def test_admin_login_is_rate_limited(browser: Callable[[], Browser]) -> None:
    b = browser()
    b.client.app.state.ctx.login_limiter = RateLimiter(5, 60)
    codes = [b.post("/api/admin/login", json={"username": "admin", "password": "x"}).status_code
             for _ in range(6)]
    assert codes[-1] == 429


def test_admin_endpoints_require_admin_session(approved_player: Callable[[str], Browser]) -> None:
    player = approved_player("NotAdmin")
    for method, path in [("GET", "/api/admin/state"), ("POST", "/api/admin/players/1/approve"),
                         ("POST", "/api/admin/players/1/revoke"),
                         ("POST", "/api/admin/host-player")]:
        assert player.request(method, path).status_code == 401, path


def test_dashboard_lists_pending_with_ip_and_history(browser: Callable[[], Browser],
                                                     admin: Browser) -> None:
    rejected = browser()
    admin.post(f"/api/admin/players/{request_access(rejected)}/reject")
    pending = browser()
    sid = request_access(pending)
    state = admin.get("/api/admin/state").json()
    assert [p["id"] for p in state["pending"]] == [sid]
    entry = state["pending"][0]
    assert entry["ip_address"] == "testclient"
    assert entry["prior_rejections"] == 1
    assert entry["online"] is False
    assert [p["status"] for p in state["players"]] == ["REJECTED"]


def test_admin_can_rename_player(approved_player: Callable[[str], Browser],
                                 admin: Browser) -> None:
    p = approved_player("Old")
    response = admin.put(f"/api/admin/players/{p.session_id}/nickname", json={"nickname": "New"})
    assert response.json()["nickname"] == "New"
    assert p.get("/api/me").json()["nickname"] == "New"


def test_host_player_identity_is_separate(admin: Browser) -> None:
    assert admin.post("/api/admin/host-player", json={"nickname": "TheHost"}).status_code == 200
    me = admin.get("/api/me").json()
    assert me["is_host"] is True and me["nickname"] == "TheHost" and me["status"] == "APPROVED"

    # The player cookie alone grants no admin rights.
    player_only = Browser(admin.client)
    player_only.cookies["lgh_player"] = admin.cookies["lgh_player"]
    assert player_only.get("/api/admin/state").status_code == 401
    # The admin cookie alone grants no player identity.
    admin_only = Browser(admin.client)
    admin_only.cookies["lgh_admin"] = admin.cookies["lgh_admin"]
    assert admin_only.get("/api/me").status_code == 401


def test_reissuing_host_player_keeps_identity_and_rotates_token(admin: Browser) -> None:
    admin.post("/api/admin/host-player", json={})
    first_token = admin.cookies["lgh_player"]
    first_id = admin.get("/api/me").json()["id"]
    admin.post("/api/admin/host-player", json={})
    assert admin.get("/api/me").json()["id"] == first_id
    stale = Browser(admin.client)
    stale.cookies["lgh_player"] = first_token
    assert stale.get("/api/me").status_code == 401


def test_state_changes_require_csrf_header(client: TestClient) -> None:
    client.headers.pop("x-requested-with")
    response = client.post("/api/access/request", json={"password": "letmein"})
    assert response.status_code == 403


def test_state_changes_reject_foreign_origin(browser: Callable[[], Browser]) -> None:
    b = browser()
    response = b.post("/api/access/request", json={"password": "letmein"},
                      headers={"origin": "http://evil.example"})
    assert response.status_code == 403


def test_bootstrap_does_not_overwrite_existing_admin(app_settings, tmp_path) -> None:  # noqa: ANN001
    from app.main import create_app

    changed = app_settings.model_copy(update={"admin_password": "a-different-password",
                                              "frontend_dist_dir": tmp_path / "none"})
    from app.api.deps import CSRF_HEADER, CSRF_VALUE

    with TestClient(create_app(app_settings.model_copy(
            update={"frontend_dist_dir": tmp_path / "none"}))):
        pass  # first start creates the admin
    with TestClient(create_app(changed), headers={CSRF_HEADER: CSRF_VALUE}) as c:
        old = c.post("/api/admin/login", json={"username": ADMIN_USERNAME,
                                               "password": ADMIN_PASSWORD})
        new = c.post("/api/admin/login", json={"username": ADMIN_USERNAME,
                                               "password": "a-different-password"})
    assert old.status_code == 200
    assert new.status_code == 401
