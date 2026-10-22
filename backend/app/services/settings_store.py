"""Host-wide settings persisted in the app_settings table."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting

MUTE_ALL_SOUND = "mute_all_sound"


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppSetting, key)
    return default if row is None else row.value


def put(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key, with_for_update=True)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.flush()
