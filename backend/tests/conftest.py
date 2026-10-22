from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from starlette.websockets import WebSocketDisconnect

from app import db
from app.api.deps import CSRF_HEADER, CSRF_VALUE
from app.config import DEFAULT_ENV_FILE, DatabaseSettings, Settings, get_database_settings, get_settings
from app.main import create_app
from app.migrations import head_revision

PLACEHOLDER_URL = "postgresql+psycopg://user:pass@127.0.0.1:1/placeholder"
ROOM_PASSWORD = "letmein"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-password-1"
SETTINGS_ENV_VARS = [name.upper() for name in Settings.model_fields]


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    db.get_engine.cache_clear()
    head_revision.cache_clear()


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the developer's real environment and .env out of tests."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setitem(DatabaseSettings.model_config, "env_file", None)
    monkeypatch.setenv("DATABASE_URL", PLACEHOLDER_URL)
    monkeypatch.setenv("ROOM_PASSWORD", ROOM_PASSWORD)
    _clear_caches()
    yield
    _clear_caches()


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"database_url": PLACEHOLDER_URL, "room_password": ROOM_PASSWORD}
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(DEFAULT_ENV_FILE).get(
        "TEST_DATABASE_URL"
    )


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """A dedicated, disposable database migrated to head once per test run."""
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    from alembic import command

    from app.migrations import alembic_config

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", url)
        mp.setitem(DatabaseSettings.model_config, "env_file", None)
        _clear_caches()
        command.upgrade(alembic_config(), "head")
        _clear_caches()
    yield url


@pytest.fixture
def database_url(migrated_database: str) -> str:
    """The test database with every application table emptied."""
    engine = create_engine(migrated_database)
    with engine.begin() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
            "AND tablename <> 'alembic_version'"
        )).scalars().all()
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    engine.dispose()
    return migrated_database


@pytest.fixture
def app_settings(database_url: str) -> Settings:
    return make_settings(
        database_url=database_url,
        admin_username=ADMIN_USERNAME,
        admin_password=ADMIN_PASSWORD,
        disconnect_grace_seconds=0,
        # All simulated browsers share one IP; rate-limit tests install real limits.
        rate_limit_access_per_minute=1000,
        rate_limit_login_per_minute=1000,
        rate_limit_actions_per_second=1000,
    )


@pytest.fixture
def client(app_settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(app_settings.model_copy(update={"frontend_dist_dir": tmp_path / "none"}))
    with TestClient(app, headers={CSRF_HEADER: CSRF_VALUE}) as test_client:
        yield test_client


class Browser:
    """One simulated browser: its own cookie jar over the shared TestClient/app."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.cookies: dict[str, str] = {}

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.cookies:
            headers["cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        return headers

    def request(self, method: str, path: str, **kwargs: Any):  # noqa: ANN201
        headers = self._headers(kwargs.pop("headers", None))
        self.client.cookies.clear()
        response = self.client.request(method, path, headers=headers, **kwargs)
        for name, value in response.cookies.items():
            if value:
                self.cookies[name] = value
            else:
                self.cookies.pop(name, None)
        for header in response.headers.get_list("set-cookie"):
            if "Max-Age=0" in header or 'expires=Thu, 01 Jan 1970' in header:
                self.cookies.pop(header.split("=", 1)[0], None)
        self.client.cookies.clear()
        return response

    def get(self, path: str, **kwargs: Any):  # noqa: ANN201
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any):  # noqa: ANN201
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any):  # noqa: ANN201
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any):  # noqa: ANN201
        return self.request("DELETE", path, **kwargs)

    def ws(self, path: str, headers: dict[str, str] | None = None):  # noqa: ANN201
        self.client.cookies.clear()
        return self.client.websocket_connect(path, headers=self._headers(headers))


@pytest.fixture
def browser(client: TestClient) -> Callable[[], Browser]:
    return lambda: Browser(client)


@pytest.fixture
def admin(browser: Callable[[], Browser]) -> Browser:
    b = browser()
    response = b.post("/api/admin/login", json={"username": ADMIN_USERNAME,
                                                "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return b


def request_access(b: Browser, password: str = ROOM_PASSWORD) -> int:
    response = b.post("/api/access/request", json={"password": password})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def approved_player(browser: Callable[[], Browser], admin: Browser) -> Callable[[str], Browser]:
    """Factory: a guest that requested access, was approved, and chose a nickname."""

    def make(nickname: str) -> Browser:
        b = browser()
        session_id = request_access(b)
        assert admin.post(f"/api/admin/players/{session_id}/approve").status_code == 200
        response = b.put("/api/me/nickname", json={"nickname": nickname})
        assert response.status_code == 200, response.text
        b.session_id = session_id  # type: ignore[attr-defined]
        return b

    return make


def receive_until(ws: Any, predicate: Callable[[dict], bool], limit: int = 50) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message not received")


def expect_close(ws: Any, code: int, limit: int = 50) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        for _ in range(limit):
            ws.receive_json()
    assert excinfo.value.code == code


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>LanGamesHub</title>")
    (dist / "assets" / "app-abc123.js").write_text("console.log('ok')")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside dist")
    return dist
