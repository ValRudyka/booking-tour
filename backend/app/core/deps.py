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

from app.core.security import decode_access_token
from app.db import get_db
from app.models import User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Same scheme, but a missing token is not an error (public endpoints that show more to some users).
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не вдалося підтвердити облікові дані",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error
    user = db.get(User, user_id)
    if user is None or not user.is_active:  # blocked users lose access immediately
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(token: Annotated[str | None, Depends(optional_oauth2_scheme)],
                      db: DbSession) -> User | None:
    """The logged-in user, or None for a guest (an invalid token also counts as a guest)."""
    if not token:
        return None
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id is not None else None
    return user if user is not None and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Allow the endpoint only for the given roles (ТЗ 4.3)."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")
        return user

    return checker
