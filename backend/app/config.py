"""Application configuration loaded from environment variables and the repo-root .env file.

Real environment variables take precedence over values in .env. Secrets are never
logged or exposed to the frontend.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
# Placeholders shipped in .env.example; refusing them prevents running with known passwords.
EXAMPLE_PASSWORDS = frozenset({"change-me", "change-me-too"})


class DatabaseSettings(BaseSettings):
    """Just the database connection; enough for Alembic and CLI tools."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        # utf-8-sig also accepts files that Windows Notepad saved with a byte-order mark.
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: SecretStr = Field(
        description="SQLAlchemy URL, e.g. postgresql+psycopg://USER:PASS@HOST:5432/DB"
    )

    @field_validator("database_url")
    @classmethod
    def _require_postgres_psycopg(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the 'postgresql+psycopg://' driver prefix")
        return value


class Settings(DatabaseSettings):
    """Full server configuration."""

    bind_host: str = "0.0.0.0"
    bind_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    frontend_dist_dir: Path = DEFAULT_FRONTEND_DIST

    # Shared password guests enter to request access. Prefer ROOM_PASSWORD_HASH
    # (argon2, generate with `python -m app.cli hash-password`) over plaintext.
    room_password: SecretStr | None = None
    room_password_hash: SecretStr | None = None

    # Used only to create the admin account when it does not exist yet. An
    # existing admin's password is never changed by these values.
    admin_username: str = "admin"
    admin_password: SecretStr | None = None

    player_session_ttl_minutes: int = Field(default=720, ge=5)
    admin_session_ttl_minutes: int = Field(default=480, ge=5)
    pending_request_ttl_minutes: int = Field(default=15, ge=1)
    # How long a disconnected room member keeps their "ready" flag.
    disconnect_grace_seconds: int = Field(default=15, ge=0)

    rate_limit_access_per_minute: int = Field(default=5, ge=1)
    rate_limit_login_per_minute: int = Field(default=5, ge=1)
    rate_limit_actions_per_second: int = Field(default=10, ge=1)

    # Set true only when the app is served over HTTPS; plain-HTTP LAN browsers
    # drop cookies marked Secure.
    cookie_secure: bool = False

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("frontend_dist_dir", mode="after")
    @classmethod
    def _resolve_dist_dir(cls, value: Path) -> Path:
        # Relative paths are interpreted relative to the repo root, not the CWD,
        # so startup scripts behave the same regardless of where they are launched.
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @field_validator("room_password", "room_password_hash", "admin_password", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _require_room_password(self) -> Settings:
        if self.room_password is None and self.room_password_hash is None:
            raise ValueError("Set ROOM_PASSWORD_HASH (preferred) or ROOM_PASSWORD")
        for name, value in (("ROOM_PASSWORD", self.room_password),
                            ("ADMIN_PASSWORD", self.admin_password)):
            if value is not None and value.get_secret_value() in EXAMPLE_PASSWORDS:
                raise ValueError(f"{name} is still the example value from .env.example")
        if self.room_password is not None and len(self.room_password.get_secret_value()) < 4:
            raise ValueError("ROOM_PASSWORD must be at least 4 characters")
        if self.admin_password is not None and len(self.admin_password.get_secret_value()) < 8:
            raise ValueError("ADMIN_PASSWORD must be at least 8 characters")
        return self


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
