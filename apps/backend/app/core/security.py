"""Password hashing (Argon2id), access tokens (short-lived JWT), opaque refresh tokens, CSRF tokens."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
_ALGORITHM = "HS256"
_ISSUER = "redstarvibe"

_hasher = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)
# Verified against when the account does not exist, so login timing does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_family: uuid.UUID
    role: str


def create_access_token(user_id: uuid.UUID, session_family: uuid.UUID, role: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_family),
        "role": role,
        "typ": "access",
        "iss": _ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=_ALGORITHM)


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def decode_access_token(token: str) -> AccessClaims:
    try:
        data = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "sid", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalid from exc
    if data.get("typ") != "access":
        raise TokenInvalid
    try:
        return AccessClaims(uuid.UUID(data["sub"]), uuid.UUID(data["sid"]), str(data.get("role", "user")))
    except (ValueError, KeyError) as exc:
        raise TokenInvalid from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Refresh tokens are stored only as a keyed hash, so a DB leak does not leak usable tokens."""
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
