from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings
from tests.conftest import PLACEHOLDER_URL, make_settings


def test_defaults() -> None:
    settings = make_settings()
    assert settings.bind_host == "0.0.0.0"
    assert settings.bind_port == 8000
    assert settings.log_level == "INFO"
    assert settings.frontend_dist_dir == REPO_ROOT / "frontend" / "dist"


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIND_PORT", "9123")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.bind_port == 9123
    assert settings.log_level == "DEBUG"


def test_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={PLACEHOLDER_URL}\nBIND_PORT=8111\n")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.bind_port == 8111


def test_environment_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={PLACEHOLDER_URL}\nBIND_PORT=8111\n")
    monkeypatch.setenv("BIND_PORT", "8222")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.bind_port == 8222


def test_database_url_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError, match="database_url"):
        Settings()  # type: ignore[call-arg]


def test_database_url_must_use_psycopg_driver() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        make_settings(database_url="postgresql://u:p@h/db")


def test_database_url_is_masked_in_repr() -> None:
    settings = make_settings(database_url="postgresql+psycopg://u:hunter2@h/db")
    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings.model_dump())


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(log_level="LOUD")


def test_relative_dist_dir_resolves_against_repo_root() -> None:
    settings = make_settings(frontend_dist_dir="custom/dist")
    assert settings.frontend_dist_dir == (REPO_ROOT / "custom" / "dist").resolve()


def test_env_example_documents_every_setting() -> None:
    import re

    text = (REPO_ROOT / ".env.example").read_text()
    documented = set(re.findall(r"^#?\s*([A-Z_]+)=", text, flags=re.M))
    expected = {name.upper() for name in Settings.model_fields} | {"TEST_DATABASE_URL"}
    assert expected <= documented, expected - documented


def test_example_passwords_are_refused() -> None:
    with pytest.raises(ValidationError, match="example value"):
        make_settings(room_password="change-me")
    with pytest.raises(ValidationError, match="example value"):
        make_settings(admin_password="change-me-too")


def test_env_file_with_windows_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"\xef\xbb\xbf" + f"DATABASE_URL={PLACEHOLDER_URL}\r\nBIND_PORT=8123\r\n".encode())
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.bind_port == 8123
    assert settings.database_url.get_secret_value() == PLACEHOLDER_URL
