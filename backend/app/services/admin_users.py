"""System administrator: user accounts and roles (ТЗ 4.3, 4.5.8, use case «Керувати правами
доступу осіб», «Додати / заблокувати акаунт співробітника»).

Rules:
- staff (manager, finance, admin) are created here; clients register themselves;
- roles change only between staff roles; a client stays a client (can be edited or blocked);
- an admin cannot block themselves or change their own role;
- the last active admin cannot be blocked or demoted (active admin rows are locked first, so two
  admins demoting each other at the same moment cannot leave none);
- no hard delete — blocking keeps the history (orders, audit log) intact;
- blocking and role changes take effect immediately: every request reads the user from the
  database; a password reset sets tokens_valid_after, so older tokens stop working.
Every change is written to the audit log (never the password).
"""
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, token_cutoff
from app.models import User
from app.models.enums import UserRole
from app.services import users as user_service
from app.services.audit import audit, changed, snapshot
from app.services.errors import DomainError
from app.services.users import UserError

STAFF_ROLES = (UserRole.MANAGER, UserRole.FINANCE, UserRole.ADMIN)
PROFILE_FIELDS = ("last_name", "first_name", "email", "phone")


def _domain(error: UserError) -> DomainError:
    return DomainError(error.message, error.status_code)


def list_users(db: Session, *, role: UserRole | None, is_active: bool | None, q: str | None,
               page: int, page_size: int) -> tuple[list[User], int]:
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
    if q and q.strip():
        term = q.strip()
        query = query.where(or_(User.last_name.icontains(term, autoescape=True),
                                User.first_name.icontains(term, autoescape=True),
                                User.email.icontains(term, autoescape=True),
                                User.phone.icontains(term.replace(" ", ""), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_user(db: Session, user_id: int, lock: bool = False) -> User:
    query = select(User).where(User.id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    user = db.scalar(query)
    if user is None:
        raise DomainError("Користувача не знайдено", 404)
    return user


def create_staff(db: Session, admin: User, data: dict[str, Any]) -> User:
    role = data["role"]
    if role not in STAFF_ROLES:
        raise DomainError("Тут створюються лише співробітники; клієнти реєструються самі", 422)
    try:
        user = user_service.create_user(db, phone=data["phone"], email=data["email"],
                                        password=data["password"], last_name=data["last_name"],
                                        first_name=data["first_name"], role=role)
    except UserError as error:
        raise _domain(error) from None
    audit(db, admin, "user", user.id, "created",
          new=snapshot(user, ("role", "last_name", "first_name", "email", "phone", "is_active")))
    return user


def _keeps_an_admin(db: Session, target: User) -> None:
    """Refuse if `target` is the last active admin."""
    admins = db.scalars(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
                        .order_by(User.id).with_for_update()).all()
    if not any(a.id != target.id for a in admins):
        raise DomainError("Це останній активний адміністратор — його не можна заблокувати "
                          "або змінити йому роль", 409)


def update_user(db: Session, admin: User, user_id: int, changes: dict[str, Any]) -> User:
    target = get_user(db, user_id, lock=True)
    changes = {k: v for k, v in changes.items() if v is not None}
    new_role, new_active = changes.get("role"), changes.get("is_active")
    role_changes = new_role is not None and new_role != target.role
    blocks = new_active is False and target.is_active

    if role_changes:
        if target.role == UserRole.CLIENT:
            raise DomainError("Роль клієнта не змінюється: співробітників створює адміністратор", 409)
        if new_role not in STAFF_ROLES:
            raise DomainError("Співробітнику можна призначити лише роль менеджера, "
                              "фінансового контролера або адміністратора", 422)
    if target.id == admin.id and (role_changes or blocks):
        raise DomainError("Не можна заблокувати себе або змінити власну роль", 409)
    if target.role == UserRole.ADMIN and target.is_active and (role_changes or blocks):
        _keeps_an_admin(db, target)

    profile = {k: v for k, v in changes.items() if k in PROFILE_FIELDS}
    try:
        if "email" in profile:
            profile["email"] = profile["email"].lower()
            user_service.ensure_unique(db, None, profile["email"], exclude_id=target.id)
        if "phone" in profile:
            user_service.ensure_unique(db, profile["phone"], None, exclude_id=target.id)
        user_service.check_name_alphabet(db, profile.get("last_name", target.last_name),
                                         profile.get("first_name", target.first_name),
                                         target.citizenship_id)
    except UserError as error:
        raise _domain(error) from None

    before = snapshot(target, PROFILE_FIELDS + ("role", "is_active"))
    for field, value in profile.items():
        setattr(target, field, value)
    if role_changes:
        target.role = new_role
    if new_active is not None:
        target.is_active = new_active
    db.flush()
    after = snapshot(target, PROFILE_FIELDS + ("role", "is_active"))

    # One audit row per kind of change, so the log can be filtered by action.
    for action, fields in (("role_changed", ("role",)), ("blocked" if blocks else "unblocked", ("is_active",)),
                           ("updated", PROFILE_FIELDS)):
        old, new = changed({f: before[f] for f in fields}, {f: after[f] for f in fields})
        if new:
            audit(db, admin, "user", target.id, action, old, new)
    return target


def reset_password(db: Session, admin: User, user_id: int, new_password: str) -> User:
    """The user changes it later via /api/auth/me/password. Tokens issued before the reset stop
    working; tokens_valid_after is in whole seconds like JWT iat, so a login in the same second
    as the reset still gets a working token."""
    target = get_user(db, user_id, lock=True)
    target.password_hash = hash_password(new_password)
    target.tokens_valid_after = token_cutoff()
    db.flush()
    # Names with "password"/"token" are never logged, so only the moment old sessions ended.
    audit(db, admin, "user", target.id, "password_reset",
          new={"sessions_ended_at": target.tokens_valid_after})
    return target
