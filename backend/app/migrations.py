"""Helpers for locating Alembic configuration and the expected schema revision."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    # Make script_location independent of the current working directory.
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@lru_cache
def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()
