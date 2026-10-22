"""Password hashing and session tokens.

Session tokens are random 256-bit values given to the browser in an HttpOnly cookie.
Only their SHA-256 digest is stored, so a database leak does not expose live sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings

_hasher = PasswordHasher()

# Verifying against this keeps response timing the same for unknown usernames.
_DUMMY_HASH = _hasher.hash("timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_room_password(settings: Settings, candidate: str) -> bool:
    if settings.room_password_hash is not None:
        return verify_password(settings.room_password_hash.get_secret_value(), candidate)
    assert settings.room_password is not None  # enforced by Settings validation
    expected = settings.room_password.get_secret_value()
    return hmac.compare_digest(expected.encode(), candidate.encode())
