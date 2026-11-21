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


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        return None
