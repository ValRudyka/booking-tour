"""FastAPI dependencies: DB session, current user, role checks.

Usage in a router:
    @router.get("/orders")
    def list_orders(db: DbSession, user: CurrentUser): ...

    @router.post("/tours", dependencies=[Depends(require_roles(UserRole.MANAGER))])
"""
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db import get_db
from app.models import User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Same scheme, but a missing token is not an error (public endpoints that show more to some users).
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def user_from_token(db: Session, token: str | None) -> User | None:
    """The active user the token belongs to, or None: invalid/expired token, unknown or blocked
    user (blocked users lose access immediately), or a token issued before the user's
    tokens_valid_after (password reset by the admin). The role is always read from the database,
    so a role change also takes effect immediately."""
    if not token:
        return None
    claims = decode_token(token)
    if claims is None:
        return None
    user_id, issued_at = claims
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    if user.tokens_valid_after is not None and (
            issued_at is None or issued_at < int(user.tokens_valid_after.timestamp())):
        return None
    return user


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    user = user_from_token(db, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Не вдалося підтвердити облікові дані",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(token: Annotated[str | None, Depends(optional_oauth2_scheme)],
                      db: DbSession) -> User | None:
    """The logged-in user, or None for a guest (an invalid token also counts as a guest)."""
    return user_from_token(db, token)


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Allow the endpoint only for the given roles (ТЗ 4.3)."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")
        return user

    return checker
