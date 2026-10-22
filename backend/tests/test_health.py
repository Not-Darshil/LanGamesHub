from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.main import create_app
from app.migrations import head_revision
from tests.conftest import make_settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # No `with`: lifespan (startup DB check) is not needed for these tests.
    return TestClient(create_app(make_settings(frontend_dist_dir=tmp_path / "none")))


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_schema_current(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda engine: head_revision())
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "migrations": "current"}


def test_not_ready_when_migrations_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "check_database", lambda engine: None)
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["migrations"] == "pending"


def test_not_ready_when_database_unreachable_and_no_details_leak(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(engine: object) -> None:
        raise RuntimeError('password authentication failed for user "secretuser"')

    monkeypatch.setattr(health, "check_database", boom)
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
    assert "secretuser" not in response.text


def test_ready_against_real_database(database_url: str, tmp_path: Path) -> None:
    """Integration: the migrated TEST_DATABASE_URL reports ready."""
    app = create_app(make_settings(database_url=database_url, frontend_dist_dir=tmp_path / "none"))
    with TestClient(app) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "database": "ok", "migrations": "current"}


def test_migrations_round_trip(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every migration downgrades cleanly and re-applies (leaves the DB at head)."""
    from alembic import command

    from app.db import check_database, get_engine
    from app.migrations import alembic_config

    monkeypatch.setenv("DATABASE_URL", migrated_database)
    config = alembic_config()
    command.downgrade(config, "base")
    assert check_database(get_engine()) is None
    command.upgrade(config, "head")
    assert check_database(get_engine()) == head_revision()
    get_engine().dispose()
