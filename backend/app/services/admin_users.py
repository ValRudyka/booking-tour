"""System administrator: user accounts and roles (ТЗ 4.3, 4.5.8, use case «Керувати правами
доступу осіб», «Додати / заблокувати акаунт співробітника»).

Rules (each is a refusal function below; the endpoints raise it and services/admin_actions.py
returns it as the reason of a disabled button, so the UI shows the rule before the request):
- staff (manager, finance, admin) are created here; clients register themselves;
- roles change only between staff roles; a client stays a client (`role_refusal`);
- a client's personal data is not edited by the admin: the client changes it in the profile
  (`edit_refusal`, spec 13 §1); a client can still be blocked or get a password reset;
- an admin cannot block themselves or change their own role, and changes their own password in
  the profile, not through the admin reset (`block_refusal`, `role_refusal`, `reset_refusal`);
- the last active admin cannot be blocked or demoted (active admin rows are locked first, so two
  admins demoting each other at the same moment cannot leave none);
- no hard delete — blocking keeps the history (orders, audit log) intact;
- blocking and a password reset set tokens_valid_after, so every token issued before stops
  working, also after an unblock. Role changes take effect at once (the role is read from the
  database on every request).
Every change is written to the audit log (never the password).
"""
import secrets
import string
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
               page: int, page_size: int, staff: bool | None = None) -> tuple[list[User], int]:
    """`staff`: True = managers, finance and admins (tab «Персонал»), False = clients."""
    query = select(User)
    if staff is not None:
        query = query.where(User.role.in_(STAFF_ROLES) if staff else User.role == UserRole.CLIENT)
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


# A temporary password the server makes for a new employee: 16 letters and digits with at least
# one lower-case letter, one capital and one digit, so it passes every password rule (backend and
# the frontend's features/auth/rules.ts). It is returned once in the create response and never
# stored in plain text or logged.
TEMP_PASSWORD_LENGTH = 16
_ALPHABET = string.ascii_letters + string.digits


def temporary_password() -> str:
    while True:
        value = "".join(secrets.choice(_ALPHABET) for _ in range(TEMP_PASSWORD_LENGTH))
        if (any(c.islower() for c in value) and any(c.isupper() for c in value)
                and any(c.isdigit() for c in value)):
            return value


def create_staff(db: Session, admin: User, data: dict[str, Any]) -> tuple[User, str | None]:
    """Returns the user and the temporary password when the server generated it (no `password`
    in the request, as the admin UI sends); a password chosen by the caller is not echoed."""
    role = data["role"]
    if role not in STAFF_ROLES:
        raise DomainError("Тут створюються лише співробітники; клієнти реєструються самі", 422)
    generated = None if data.get("password") else temporary_password()
    try:
        user = user_service.create_user(db, phone=data["phone"], email=data["email"],
                                        password=generated or data["password"],
                                        last_name=data["last_name"], first_name=data["first_name"],
                                        role=role)
    except UserError as error:
        raise _domain(error) from None
    audit(db, admin, "user", user.id, "created",
          new=snapshot(user, ("role", "last_name", "first_name", "email", "phone", "is_active")))
    return user, generated


# ---------- safety rules (the endpoints raise them, admin_actions shows them as reasons)
LAST_ADMIN = "Це останній активний адміністратор — його не можна заблокувати або змінити йому роль"


def active_admin_ids(db: Session, lock: bool = False) -> set[int]:
    query = select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).order_by(User.id)
    if lock:
        query = query.with_for_update()
    return set(db.scalars(query))


def _last_admin(target: User, admin_ids: set[int]) -> bool:
    return target.role == UserRole.ADMIN and target.is_active and not (admin_ids - {target.id})


def edit_refusal(target: User) -> str | None:
    if target.role == UserRole.CLIENT:
        return "Особисті дані клієнт змінює сам у профілі; телефон — через підтримку"
    return None


def role_refusal(admin: User, target: User, admin_ids: set[int]) -> str | None:
    if target.role == UserRole.CLIENT:
        return "Роль клієнта не змінюється: співробітників створює адміністратор"
    if target.id == admin.id:
        return "Не можна змінити власну роль"
    if _last_admin(target, admin_ids):
        return LAST_ADMIN
    return None


def block_refusal(admin: User, target: User, admin_ids: set[int]) -> str | None:
    if target.id == admin.id:
        return "Не можна заблокувати себе"
    if _last_admin(target, admin_ids):
        return LAST_ADMIN
    return None


def reset_refusal(admin: User, target: User) -> str | None:
    if target.id == admin.id:
        return "Власний пароль змініть через «Змінити пароль» у меню профілю"
    return None


def update_user(db: Session, admin: User, user_id: int, changes: dict[str, Any]) -> User:
    target = get_user(db, user_id, lock=True)
    changes = {k: v for k, v in changes.items() if v is not None}
    new_role, new_active = changes.get("role"), changes.get("is_active")
    role_changes = new_role is not None and new_role != target.role
    blocks = new_active is False and target.is_active
    profile = {k: v for k, v in changes.items() if k in PROFILE_FIELDS}

    if profile and (reason := edit_refusal(target)):
        raise DomainError(reason, 409)
    if role_changes and target.role != UserRole.CLIENT and new_role not in STAFF_ROLES:
        raise DomainError("Співробітнику можна призначити лише роль менеджера, "
                          "фінансового контролера або адміністратора", 422)
    if role_changes or blocks:
        # The active admin rows are locked when the last-admin rule can matter.
        admin_ids = active_admin_ids(db, lock=target.role == UserRole.ADMIN)
        reason = ((role_refusal(admin, target, admin_ids) if role_changes else None)
                  or (block_refusal(admin, target, admin_ids) if blocks else None))
        if reason:
            raise DomainError(reason, 409)

    try:
        if "email" in profile:
            profile["email"] = profile["email"].lower()
            user_service.ensure_unique(db, None, profile["email"], exclude_id=target.id)
        if "phone" in profile:
            user_service.ensure_unique(db, profile["phone"], None, exclude_id=target.id)
        if profile:
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
    if blocks:
        # Every token issued before the block stays invalid after an unblock too.
        target.tokens_valid_after = token_cutoff()
    db.flush()
    after = snapshot(target, PROFILE_FIELDS + ("role", "is_active"))

    # One audit row per kind of change, so the log can be filtered by action.
    for action, fields in (("role_changed", ("role",)), ("blocked" if blocks else "unblocked", ("is_active",)),
                           ("updated", PROFILE_FIELDS)):
        old, new = changed({f: before[f] for f in fields}, {f: after[f] for f in fields})
        if new:
            if action == "blocked":
                new["sessions_ended_at"] = target.tokens_valid_after
            audit(db, admin, "user", target.id, action, old, new)
    return target


def reset_password(db: Session, admin: User, user_id: int, new_password: str) -> User:
    """The user changes it later via /api/auth/me/password. Tokens issued before the reset stop
    working; tokens_valid_after is in whole seconds like JWT iat, so a login in the same second
    as the reset still gets a working token."""
    target = get_user(db, user_id, lock=True)
    if reason := reset_refusal(admin, target):
        raise DomainError(reason, 409)
    target.password_hash = hash_password(new_password)
    target.tokens_valid_after = token_cutoff()
    db.flush()
    # Names with "password"/"token" are never logged, so only the moment old sessions ended.
    audit(db, admin, "user", target.id, "password_reset",
          new={"sessions_ended_at": target.tokens_valid_after})
    return target
