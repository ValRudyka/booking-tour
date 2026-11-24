"""Password hashing (Argon2 via pwdlib) and JWT access tokens (PyJWT).

Follows the FastAPI security tutorial: pwdlib replaces the unmaintained passlib.
"""
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.config import settings

password_hash = PasswordHash.recommended()  # Argon2id

# Used when the login does not exist, so the response takes the same time
# whether the user exists or not (prevents user enumeration by timing).
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None,
                        issued_at: datetime | None = None) -> str:
    """`iat` (issued at, whole seconds) lets the server reject tokens issued before a password
    reset (users.tokens_valid_after). `issued_at` is for tests only."""
    now = issued_at or datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": str(user_id), "role": role, "iat": int(now.timestamp()), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> tuple[int, int | None] | None:
    """(user id, iat in whole seconds or None) from a valid token, None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        iat = payload.get("iat")
        return int(payload["sub"]), int(iat) if iat is not None else None
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        return None


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if the token is invalid/expired."""
    claims = decode_token(token)
    return claims[0] if claims else None


def token_cutoff(now: datetime | None = None) -> datetime:
    """Value for users.tokens_valid_after: now truncated to whole seconds, because JWT iat has
    whole-second precision. A token issued in the same second as the reset is accepted
    (iat == cut-off); one issued in an earlier second is rejected (iat < cut-off)."""
    return (now or datetime.now(timezone.utc)).replace(microsecond=0)
