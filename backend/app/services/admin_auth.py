"""Admin account bootstrap, login, and session validation."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AdminSession, AdminUser
from app.security import hash_password, new_token, token_digest, verify_password
from app.timeutil import utcnow

logger = logging.getLogger(__name__)


def bootstrap_admin(db: Session, settings: Settings) -> str:
    """Create the configured admin if missing. Returns 'created', 'exists' or 'missing'."""
    existing = db.scalar(select(AdminUser).where(AdminUser.username == settings.admin_username))
    if existing is not None:
        return "exists"
    if settings.admin_password is None:
        return "missing"
    db.add(AdminUser(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password.get_secret_value()),
    ))
    db.flush()
    logger.info("Created admin account %r from bootstrap credentials", settings.admin_username)
    return "created"


def set_admin_password(db: Session, username: str, password: str) -> None:
    admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if admin is None:
        db.add(AdminUser(username=username, password_hash=hash_password(password)))
    else:
        admin.password_hash = hash_password(password)
        # A password change ends every existing admin session.
        for session in db.scalars(select(AdminSession).where(
                AdminSession.admin_id == admin.id, AdminSession.revoked_at.is_(None))):
            session.revoked_at = utcnow()
    db.flush()


def login(db: Session, settings: Settings, username: str, password: str, ip: str) -> str | None:
    admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not verify_password(admin.password_hash if admin else None, password) or admin is None:
        logger.warning("Failed admin login for %r from %s", username, ip)
        return None
    token = new_token()
    now = utcnow()
    db.add(AdminSession(
        admin_id=admin.id,
        token_hash=token_digest(token),
        ip_address=ip,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.admin_session_ttl_minutes),
    ))
    db.flush()
    logger.info("Admin %r logged in from %s", username, ip)
    return token


def authenticate(db: Session, token: str | None) -> AdminSession | None:
    if not token:
        return None
    session = db.scalar(select(AdminSession).where(AdminSession.token_hash == token_digest(token)))
    if session is None or session.revoked_at is not None or session.expires_at <= utcnow():
        return None
    return session


def is_active(db: Session, admin_session_id: int) -> bool:
    session = db.get(AdminSession, admin_session_id)
    return bool(session and session.revoked_at is None and session.expires_at > utcnow())


def logout(db: Session, token: str | None) -> None:
    session = authenticate(db, token)
    if session is not None:
        session.revoked_at = utcnow()
