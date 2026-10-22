"""Guest access requests, host decisions, nicknames, and player session lifecycle.

Every protected operation must go through ``authorize`` (or check ``effective_status``):
the frontend's blank page for rejected guests is presentation only.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import PlayerSession, ScreenVisibility, SessionStatus
from app.security import new_token, token_digest
from app.services.errors import Conflict, Forbidden, NotFound, ServiceError
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

EXPIRED = "EXPIRED"
NICKNAME_MAX = 20
_NICKNAME_RE = re.compile(r"^[\w][\w .\-]*$")
# Arbitrary constant key for the advisory lock that serializes nickname claims.
_NICKNAME_LOCK_KEY = 0x4C474831


def effective_status(session: PlayerSession) -> str:
    """Stored status, except live sessions past their expiry read as EXPIRED."""
    if session.status in (SessionStatus.PENDING, SessionStatus.APPROVED) and (
        session.expires_at <= utcnow()
    ):
        return EXPIRED
    return session.status.value


def find_by_token(db: Session, token: str | None) -> PlayerSession | None:
    if not token:
        return None
    return db.scalar(select(PlayerSession).where(PlayerSession.token_hash == token_digest(token)))


def get_for_update(db: Session, session_id: int) -> PlayerSession:
    session = db.get(PlayerSession, session_id, with_for_update=True)
    if session is None:
        raise NotFound("Player not found")
    return session


def request_access(db: Session, settings: Settings, ip: str, user_agent: str) -> tuple[str, PlayerSession]:
    token = new_token()
    now = utcnow()
    session = PlayerSession(
        token_hash=token_digest(token),
        status=SessionStatus.PENDING,
        ip_address=ip,
        user_agent=user_agent[:256],
        created_at=now,
        expires_at=now + timedelta(minutes=settings.pending_request_ttl_minutes),
        is_host=False,
    )
    db.add(session)
    db.flush()
    logger.info("Access request %s from %s", session.id, ip)
    return token, session


def approve(db: Session, settings: Settings, session_id: int) -> PlayerSession:
    session = get_for_update(db, session_id)
    status = effective_status(session)
    if status == SessionStatus.APPROVED:
        return session  # idempotent
    if status != SessionStatus.PENDING:
        raise Conflict(f"Request is {status.lower()} and cannot be approved")
    now = utcnow()
    session.status = SessionStatus.APPROVED
    session.decided_at = now
    session.expires_at = now + timedelta(minutes=settings.player_session_ttl_minutes)
    logger.info("Approved player session %s (%s)", session.id, session.ip_address)
    return session


def reject(db: Session, session_id: int) -> PlayerSession:
    session = get_for_update(db, session_id)
    status = effective_status(session)
    if status == SessionStatus.REJECTED:
        return session
    if status != SessionStatus.PENDING:
        raise Conflict(f"Request is {status.lower()} and cannot be rejected")
    session.status = SessionStatus.REJECTED
    session.decided_at = utcnow()
    logger.info("Rejected access request %s (%s)", session.id, session.ip_address)
    return session


def revoke(db: Session, session_id: int) -> PlayerSession:
    session = get_for_update(db, session_id)
    if session.status == SessionStatus.REVOKED:
        return session
    if session.status == SessionStatus.REJECTED:
        raise Conflict("Request was rejected; there is no session to revoke")
    session.status = SessionStatus.REVOKED
    session.decided_at = utcnow()
    logger.info("Revoked player session %s (%s)", session.id, session.ip_address)
    return session


def normalize_nickname(raw: str) -> str:
    nickname = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not nickname:
        raise ServiceError("Nickname cannot be empty")
    if len(nickname) > NICKNAME_MAX:
        raise ServiceError(f"Nickname must be at most {NICKNAME_MAX} characters")
    if not _NICKNAME_RE.match(nickname):
        raise ServiceError("Nickname may contain letters, digits, spaces, '.', '-' and '_'")
    return nickname


def set_nickname(db: Session, session: PlayerSession, raw: str) -> PlayerSession:
    nickname = normalize_nickname(raw)
    # Serialize claims so two players cannot take the same name concurrently.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _NICKNAME_LOCK_KEY})
    taken = db.scalar(
        select(PlayerSession.id).where(
            func.lower(PlayerSession.nickname) == nickname.lower(),
            PlayerSession.id != session.id,
            PlayerSession.status == SessionStatus.APPROVED,
            PlayerSession.expires_at > utcnow(),
        )
    )
    if taken is not None:
        raise Conflict("That nickname is already in use")
    session.nickname = nickname
    return session


def guest_set_nickname(db: Session, session: PlayerSession, raw: str) -> PlayerSession:
    """Guests choose a name once; later changes are the host's call (prevents mid-game swaps)."""
    session = get_for_update(db, session.id)
    if session.nickname is not None:
        raise Conflict("Nickname already set; ask the host to change it")
    return set_nickname(db, session, raw)


def authorize(session: PlayerSession | None, *, allow_pending: bool = False) -> PlayerSession:
    """Raise unless the session may use protected player features."""
    if session is None:
        raise NotAuthenticated()
    status = effective_status(session)
    if status == SessionStatus.APPROVED or (allow_pending and status == SessionStatus.PENDING):
        return session
    if status == EXPIRED:
        raise NotAuthenticated()
    raise Forbidden("Forbidden")


class NotAuthenticated(ServiceError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("Not authenticated")


def touch(db: Session, settings: Settings, session: PlayerSession, ip: str) -> None:
    """Record activity and slide the expiry forward for approved sessions."""
    now = utcnow()
    ttl = timedelta(minutes=settings.player_session_ttl_minutes)
    changed = session.ip_address != ip or session.last_seen_at is None or (
        now - session.last_seen_at > timedelta(minutes=1)
    )
    if session.status == SessionStatus.APPROVED and session.expires_at - now < ttl / 2:
        session.expires_at = now + ttl
        changed = True
    if changed:
        session.ip_address = ip
        session.last_seen_at = now


def issue_host_player(db: Session, settings: Settings, nickname: str | None, ip: str) -> str:
    """Give the host a player identity, separate from their admin session.

    Re-issuing rotates the token of the existing host player so room membership is kept
    and any older host browser tab is signed out of the player identity.
    """
    now = utcnow()
    token = new_token()
    session = db.scalar(
        select(PlayerSession)
        .where(PlayerSession.is_host.is_(True), PlayerSession.status == SessionStatus.APPROVED,
               PlayerSession.expires_at > now)
        .order_by(PlayerSession.id.desc())
        .with_for_update()
    )
    if session is None:
        session = PlayerSession(
            status=SessionStatus.APPROVED,
            is_host=True,
            ip_address=ip,
            user_agent="host",
            created_at=now,
            decided_at=now,
            token_hash=token_digest(token),
            expires_at=now + timedelta(minutes=settings.player_session_ttl_minutes),
        )
        db.add(session)
        db.flush()
        set_nickname(db, session, nickname or "Host")
    else:
        session.token_hash = token_digest(token)
        session.expires_at = now + timedelta(minutes=settings.player_session_ttl_minutes)
        if nickname and nickname != session.nickname:
            set_nickname(db, session, nickname)
    db.flush()
    return token


def set_screen_visibility(db: Session, session_id: int, visibility: ScreenVisibility) -> bool:
    """Host-only Guest Screen Hide. Idempotent; returns True if the value changed.

    This changes only what the server shows the guest's LanGamesHub page. It does not
    touch game state, turns, room membership, or the session's authorization.
    """
    session = get_for_update(db, session_id)
    if effective_status(session) != SessionStatus.APPROVED:
        raise Conflict("Only approved, active players can have their screen hidden or restored")
    if session.screen_visibility == visibility:
        return False
    session.screen_visibility = visibility
    logger.info("Screen for player session %s set to %s", session.id, visibility.value)
    return True


def report_sound(db: Session, session_id: int, enabled: bool) -> bool:
    """The guest's browser reports whether its sound effects are on. Returns True if changed."""
    session = authorize(get_for_update(db, session_id))
    if session.sound_enabled == enabled:
        return False
    session.sound_enabled = enabled
    return True


def set_sound_muted(db: Session, session_id: int, muted: bool) -> bool:
    """Host mutes or unmutes one guest's sound effects. Idempotent; True if changed."""
    session = get_for_update(db, session_id)
    if effective_status(session) != SessionStatus.APPROVED:
        raise Conflict("Only approved, active players can be muted or unmuted")
    if session.sound_muted_by_host == muted:
        return False
    session.sound_muted_by_host = muted
    logger.info("Sound for player session %s %s by the host", session.id,
                "muted" if muted else "unmuted")
    return True
