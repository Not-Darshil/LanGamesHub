"""Guest access flow: shared password, pending queue, host decision, nickname, expiry."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import create_engine, update

from app.models import PlayerSession
from app.ratelimit import RateLimiter
from app.timeutil import utcnow
from tests.conftest import Browser, request_access


def _expire(database_url: str, session_id: int) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(update(PlayerSession).where(PlayerSession.id == session_id)
                     .values(expires_at=utcnow() - timedelta(seconds=1)))
    engine.dispose()


def test_wrong_password_is_rejected_without_session(browser: Callable[[], Browser]) -> None:
    b = browser()
    response = b.post("/api/access/request", json={"password": "nope"})
    assert response.status_code == 401
    assert "lgh_player" not in b.cookies
    assert b.get("/api/me").status_code == 401


def test_correct_password_creates_pending_request(browser: Callable[[], Browser]) -> None:
    b = browser()
    response = b.post("/api/access/request", json={"password": "letmein"})
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    assert "lgh_player" in b.cookies
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie
    assert b.get("/api/me").json()["status"] == "PENDING"


def test_access_requests_are_rate_limited(browser: Callable[[], Browser]) -> None:
    b = browser()
    b.client.app.state.ctx.access_limiter = RateLimiter(5, 60)
    codes = [b.post("/api/access/request", json={"password": "bad"}).status_code
             for _ in range(6)]
    assert codes == [401] * 5 + [429]
    # Even the right password is refused while limited.
    assert b.post("/api/access/request", json={"password": "letmein"}).status_code == 429


def test_repeat_request_with_live_cookie_reuses_session(browser: Callable[[], Browser]) -> None:
    b = browser()
    first = request_access(b)
    response = b.post("/api/access/request", json={"password": "anything"})
    assert response.status_code == 201
    assert response.json()["id"] == first


def test_pending_guest_cannot_use_protected_features(browser: Callable[[], Browser]) -> None:
    b = browser()
    request_access(b)
    assert b.put("/api/me/nickname", json={"nickname": "Sneaky"}).status_code == 403


def test_approved_guest_chooses_nickname_once(browser: Callable[[], Browser],
                                              admin: Browser) -> None:
    b = browser()
    sid = request_access(b)
    assert admin.post(f"/api/admin/players/{sid}/approve").json()["status"] == "APPROVED"
    assert b.get("/api/me").json()["status"] == "APPROVED"
    response = b.put("/api/me/nickname", json={"nickname": "  Ada   Lovelace "})
    assert response.status_code == 200
    assert response.json()["nickname"] == "Ada Lovelace"
    assert b.put("/api/me/nickname", json={"nickname": "Other"}).status_code == 409


def test_nickname_validation_and_uniqueness(approved_player: Callable[[str], Browser],
                                            browser: Callable[[], Browser],
                                            admin: Browser) -> None:
    approved_player("Grace")
    b = browser()
    sid = request_access(b)
    admin.post(f"/api/admin/players/{sid}/approve")
    assert b.put("/api/me/nickname", json={"nickname": "grace"}).status_code == 409
    assert b.put("/api/me/nickname", json={"nickname": "<script>"}).status_code == 400
    assert b.put("/api/me/nickname", json={"nickname": "x" * 21}).status_code == 400
    assert b.put("/api/me/nickname", json={"nickname": "   "}).status_code == 400
    assert b.put("/api/me/nickname", json={"nickname": "Grace2"}).status_code == 200


def test_rejected_guest_stays_unauthorized(browser: Callable[[], Browser], admin: Browser) -> None:
    b = browser()
    sid = request_access(b)
    assert admin.post(f"/api/admin/players/{sid}/reject").json()["status"] == "REJECTED"
    assert b.get("/api/me").status_code == 403
    assert b.put("/api/me/nickname", json={"nickname": "Nope"}).status_code == 403
    # Asking again with the same browser does not create a fresh request.
    assert b.post("/api/access/request", json={"password": "letmein"}).status_code == 403
    # A rejection cannot be turned into an approval afterwards.
    assert admin.post(f"/api/admin/players/{sid}/approve").status_code == 409


def test_revoked_player_loses_access(approved_player: Callable[[str], Browser],
                                     admin: Browser) -> None:
    p = approved_player("Linus")
    assert admin.post(f"/api/admin/players/{p.session_id}/revoke").json()["status"] == "REVOKED"
    assert p.get("/api/me").status_code == 403
    assert p.post("/api/access/request", json={"password": "letmein"}).status_code == 403


def test_expired_pending_request_cannot_be_approved(browser: Callable[[], Browser],
                                                    admin: Browser, database_url: str) -> None:
    b = browser()
    sid = request_access(b)
    _expire(database_url, sid)
    assert b.get("/api/me").status_code == 401
    assert admin.post(f"/api/admin/players/{sid}/approve").status_code == 409
    # The guest can start over with a new request.
    assert b.post("/api/access/request", json={"password": "letmein"}).status_code == 201


def test_expired_approved_session_is_unauthenticated(approved_player: Callable[[str], Browser],
                                                     database_url: str) -> None:
    p = approved_player("Expiring")
    _expire(database_url, p.session_id)
    assert p.get("/api/me").status_code == 401


def test_session_expiry_slides_with_activity(approved_player: Callable[[str], Browser],
                                             database_url: str) -> None:
    p = approved_player("Active")
    engine = create_engine(database_url)
    soon = utcnow() + timedelta(minutes=10)
    with engine.begin() as conn:
        conn.execute(update(PlayerSession).where(PlayerSession.id == p.session_id)
                     .values(expires_at=soon))
    assert p.get("/api/me").status_code == 200
    with engine.connect() as conn:
        expires = conn.execute(PlayerSession.__table__.select()
                               .where(PlayerSession.id == p.session_id)).one().expires_at
    engine.dispose()
    assert expires > soon + timedelta(hours=1)


def test_forged_cookie_is_unauthenticated(browser: Callable[[], Browser]) -> None:
    b = browser()
    b.cookies["lgh_player"] = "forged-token"
    assert b.get("/api/me").status_code == 401
