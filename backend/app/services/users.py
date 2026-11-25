"""User business rules: registration, authentication, profile changes."""
import re
from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.models import Country, User
from app.models.enums import UserRole
from app.services import clock


class UserError(Exception):
    """Business-rule violation; routers turn it into an HTTP error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


ADULT_AGE = 18
NOT_ADULT = f"Реєстрація доступна лише з {ADULT_AGE} років"


def age_on(birth_date: date, day: date) -> int:
    """Full years on `day` (a 29 February birthday counts from 1 March in other years)."""
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def check_adult(birth_date: date | None) -> None:
    """ТЗ form 4.6.1.1, field 6: the client must be 18 or older, by the Kyiv business date."""
    if birth_date is not None and age_on(birth_date, clock.today()) < ADULT_AGE:
        raise UserError(NOT_ADULT, 422)


CYRILLIC_NAME = re.compile(r"^[А-ЩЬЮЯҐЄІЇа-щьюяґєії'’ʼ\- ]+$")
LATIN_NAME = re.compile(r"^[A-Za-z'’\- ]+$")


def check_name_alphabet(db: Session, last_name: str, first_name: str, citizenship_id: int | None) -> None:
    """ТЗ 4.5.1: Ukrainian citizens enter names in Ukrainian, others in Latin letters."""
    if citizenship_id is None:
        return
    country = db.get(Country, citizenship_id)
    if country is None:
        raise UserError("Невідома країна громадянства", 422)
    pattern, hint = ((CYRILLIC_NAME, "українською мовою") if country.iso_code == "UA"
                     else (LATIN_NAME, "латиницею"))
    for value in (last_name, first_name):
        if not pattern.match(value):
            raise UserError(f"Прізвище та ім'я потрібно вводити {hint}", 422)


def ensure_unique(db: Session, phone: str | None, email: str | None, exclude_id: int | None = None) -> None:
    conditions = []
    if phone:
        conditions.append(User.phone == phone)
    if email:
        conditions.append(User.email == email.lower())
    if not conditions:
        return
    query = select(User).where(or_(*conditions))
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    existing = db.scalars(query).first()
    if existing is not None:
        field = "телефоном" if phone and existing.phone == phone else "e-mail"
        raise UserError(f"Користувач з таким {field} вже існує", 409)


def create_user(db: Session, *, phone: str, email: str, password: str, last_name: str,
                first_name: str, role: UserRole = UserRole.CLIENT, birth_date=None,
                citizenship_id: int | None = None, consent: bool = False) -> User:
    if role == UserRole.CLIENT:
        check_adult(birth_date)
    check_name_alphabet(db, last_name, first_name, citizenship_id)
    ensure_unique(db, phone, email)
    user = User(phone=phone, email=email.lower(), password_hash=hash_password(password), role=role,
                last_name=last_name, first_name=first_name, birth_date=birth_date,
                citizenship_id=citizenship_id, consent_at=datetime.now(timezone.utc) if consent else None)
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, login: str, password: str) -> User | None:
    """Login by phone or e-mail. Returns None for any failure (no hint which part was wrong)."""
    login = login.strip()
    if "@" in login:
        user = db.scalar(select(User).where(User.email == login.lower()))
    else:
        phone = re.sub(r"[\s\-()]", "", login)
        user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        verify_password(password, DUMMY_HASH)  # same timing as a real check
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def update_profile(db: Session, user: User, changes: dict) -> User:
    # Required fields cannot be cleared; optional ones (birth_date, citizenship_id) can.
    changes = {k: v for k, v in changes.items()
               if v is not None or k in ("birth_date", "citizenship_id")}
    last_name = changes.get("last_name", user.last_name)
    first_name = changes.get("first_name", user.first_name)
    citizenship_id = changes.get("citizenship_id", user.citizenship_id)
    check_name_alphabet(db, last_name, first_name, citizenship_id)
    if changes.get("birth_date") is not None and user.role == UserRole.CLIENT:
        check_adult(changes["birth_date"])
    if "email" in changes and changes["email"]:
        changes["email"] = changes["email"].lower()
        ensure_unique(db, None, changes["email"], exclude_id=user.id)
    for field, value in changes.items():
        setattr(user, field, value)
    db.flush()
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise UserError("Поточний пароль невірний", 400)
    user.password_hash = hash_password(new)
    db.flush()
