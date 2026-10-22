"""Host maintenance CLI: diagnose, password hashing, admin password, backup/restore."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app import cli
from app.security import verify_password


@pytest.fixture
def cli_env(database_url: str, dist_dir: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(dist_dir))
    monkeypatch.setenv("ADMIN_PASSWORD", "bootstrap-pass")
    monkeypatch.setenv("BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("BIND_PORT", "8799")
    return database_url


def test_diagnose_passes_on_healthy_setup(cli_env: str, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["diagnose"]) == 0
    out = capsys.readouterr().out
    assert "[PASS] PostgreSQL connection works" in out
    assert "[PASS] Schema revision" in out and "All checks passed." in out
    assert "Guest URL: http://127.0.0.1:8799" in out
    assert "postgres:postgres" not in out  # never prints credentials


def test_diagnose_reports_unreachable_database(cli_env: str, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secret@127.0.0.1:1/none")
    assert cli.main(["diagnose"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] Cannot connect to PostgreSQL" in out and "secret" not in out


def test_hash_password_output_verifies(monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "party-time")
    assert cli.main(["hash-password"]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines()
                if x.startswith("ROOM_PASSWORD_HASH="))
    assert verify_password(line.split("=", 1)[1], "party-time")


def test_set_admin_password(cli_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "new-admin-pass")
    assert cli.main(["set-admin-password", "--username", "operator"]) == 0
    engine = create_engine(cli_env)
    with engine.connect() as conn:
        stored = conn.execute(text(
            "SELECT password_hash FROM admin_users WHERE username = 'operator'")).scalar_one()
    engine.dispose()
    assert verify_password(stored, "new-admin-pass")


@pytest.mark.skipif(shutil.which("pg_dump") is None and not list(
    Path("/Library/PostgreSQL").glob("*/bin/pg_dump")), reason="pg_dump not available")
def test_backup_and_restore_round_trip(cli_env: str, tmp_path: Path,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(cli_env)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO admin_users (username, password_hash) "
                          "VALUES ('keepme', 'x')"))
    assert cli.main(["backup", "--out", str(tmp_path)]) == 0
    dump = next(tmp_path.glob("langameshub-*.dump"))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM admin_users"))
    monkeypatch.setattr("builtins.input", lambda: "no")
    assert cli.main(["restore", str(dump)]) == 1  # wrong confirmation: nothing happens
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM admin_users")).scalar_one() == 0
    monkeypatch.setattr("builtins.input", lambda: "RESTORE")
    assert cli.main(["restore", str(dump)]) == 0
    with engine.connect() as conn:
        names = conn.execute(text("SELECT username FROM admin_users")).scalars().all()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert names == ["keepme"]
    assert revision  # schema version restored with the data
