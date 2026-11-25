"""System administrator: users and roles (ТЗ 4.3, 4.5.8). Role admin only.

Every user in a response carries `user_actions` (services/admin_actions.py): what the admin may do
with that user now, with the reason when a safety rule refuses it."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.admin import AdminUserOut, PasswordReset, StaffCreate, StaffCreatedOut, UserPatch
from app.schemas.common import Page
from app.services import admin_actions
from app.services import admin_users as service
from app.services.errors import DomainError

router = APIRouter(prefix="/admin/users", tags=["admin: users"])

Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _one(db, admin: User, user: User) -> dict:
    return admin_actions.with_user_actions(db, admin, [user])[0]


@router.get("", response_model=Page[AdminUserOut], summary="Користувачі (фільтри, пошук)")
def list_users(db: DbSession, admin: Admin,
               role: UserRole | None = None,
               staff: Annotated[bool | None, Query(description="true — персонал, false — клієнти")] = None,
               is_active: Annotated[bool | None, Query(description="false — заблоковані")] = None,
               q: Annotated[str | None, Query(max_length=100, description="Ім'я, телефон або e-mail")] = None,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = service.list_users(db, role=role, staff=staff, is_active=is_active, q=q, page=page,
                                      page_size=page_size)
    return Page(items=admin_actions.with_user_actions(db, admin, items), total=total, page=page,
                page_size=page_size)


@router.get("/{user_id}", response_model=AdminUserOut, summary="Користувач")
def get_user(user_id: int, db: DbSession, admin: Admin):
    try:
        return _one(db, admin, service.get_user(db, user_id))
    except DomainError as error:
        _raise(error)


@router.post("", response_model=StaffCreatedOut, status_code=status.HTTP_201_CREATED,
             summary="Створити співробітника (менеджер, фінансист, адміністратор)",
             description="Без `password` сервер генерує тимчасовий пароль і повертає його один раз "
                         "у `temporary_password`; він не зберігається відкритим текстом і не пишеться в журнал.")
def create_staff(data: StaffCreate, db: DbSession, admin: Admin):
    try:
        user, temporary = service.create_staff(db, admin, data.model_dump())
    except DomainError as error:
        _raise(error)
    db.commit()
    return {**_one(db, admin, user), "temporary_password": temporary}


@router.patch("/{user_id}", response_model=AdminUserOut,
              summary="Змінити роль, заблокувати / розблокувати, редагувати дані співробітника")
def update_user(user_id: int, data: UserPatch, db: DbSession, admin: Admin):
    try:
        user = service.update_user(db, admin, user_id, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return _one(db, admin, user)


@router.post("/{user_id}/reset-password", response_model=AdminUserOut,
             summary="Встановити новий пароль (старі сесії завершуються)")
def reset_password(user_id: int, data: PasswordReset, db: DbSession, admin: Admin):
    try:
        user = service.reset_password(db, admin, user_id, data.new_password)
    except DomainError as error:
        _raise(error)
    db.commit()
    return _one(db, admin, user)
