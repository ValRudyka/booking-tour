"""System administrator: users and roles (ТЗ 4.3, 4.5.8). Role admin only."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.admin import AdminUserOut, PasswordReset, StaffCreate, UserPatch
from app.schemas.common import Page
from app.services import admin_users as service
from app.services.errors import DomainError

router = APIRouter(prefix="/admin/users", tags=["admin: users"])

Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


@router.get("", response_model=Page[AdminUserOut], summary="Користувачі (фільтри, пошук)")
def list_users(db: DbSession, _: Admin,
               role: UserRole | None = None,
               is_active: Annotated[bool | None, Query(description="false — заблоковані")] = None,
               q: Annotated[str | None, Query(max_length=100, description="Ім'я, телефон або e-mail")] = None,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = service.list_users(db, role=role, is_active=is_active, q=q, page=page,
                                      page_size=page_size)
    return Page(items=[AdminUserOut.model_validate(u) for u in items], total=total, page=page,
                page_size=page_size)


@router.get("/{user_id}", response_model=AdminUserOut, summary="Користувач")
def get_user(user_id: int, db: DbSession, _: Admin):
    try:
        return service.get_user(db, user_id)
    except DomainError as error:
        _raise(error)


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED,
             summary="Створити співробітника (менеджер, фінансист, адміністратор)")
def create_staff(data: StaffCreate, db: DbSession, admin: Admin):
    try:
        user = service.create_staff(db, admin, data.model_dump())
    except DomainError as error:
        _raise(error)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=AdminUserOut,
              summary="Змінити роль, заблокувати / розблокувати, редагувати дані")
def update_user(user_id: int, data: UserPatch, db: DbSession, admin: Admin):
    try:
        user = service.update_user(db, admin, user_id, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=AdminUserOut,
             summary="Встановити новий пароль (старі сесії завершуються)")
def reset_password(user_id: int, data: PasswordReset, db: DbSession, admin: Admin):
    try:
        user = service.reset_password(db, admin, user_id, data.new_password)
    except DomainError as error:
        _raise(error)
    db.commit()
    return user
