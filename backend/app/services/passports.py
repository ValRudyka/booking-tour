"""Saved foreign passports for checkout autofill (ТЗ form 4.6.1.1, field 8) and the passport rules
shared with the checkout (form 4.6.1.2, fields 3.2–3.4)."""
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SavedPassport, User
from app.services import clock
from app.services.errors import DomainError

LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z '\-]*$")
PASSPORT_NUMBER = re.compile(r"^[A-Z0-9]{4,20}$")
AUTHORITY_CODE = re.compile(r"^\d{4}$")
MAX_SAVED_PASSPORTS = 20


def clean_latin_name(value: str) -> str:
    """Fields 8.1–8.2 / 3.2–3.3: Latin letters as in the foreign passport."""
    value = " ".join(value.split())
    if not LATIN_NAME.match(value) or len(value) > 100:
        raise DomainError("Прізвище та ім'я — латиницею, як у закордонному паспорті", 422)
    return value


def clean_passport_number(value: str) -> str:
    """Field 8.3 / 3.4: letters and digits without spaces (spaces are removed, letters upper-cased)."""
    value = "".join(value.split()).upper()
    if not PASSPORT_NUMBER.match(value):
        raise DomainError("Серія та номер паспорта — лише латинські літери й цифри, 4–20 символів", 422)
    return value


def list_passports(db: Session, user: User) -> Sequence[SavedPassport]:
    return db.scalars(select(SavedPassport).where(SavedPassport.user_id == user.id)
                      .order_by(SavedPassport.id)).all()


def add_passport(db: Session, user: User, data: dict[str, Any]) -> SavedPassport:
    authority = (data.get("issuing_authority") or "").strip() or None
    if authority is not None and not AUTHORITY_CODE.match(authority):
        raise DomainError("Орган, що видав, — 4-значний цифровий код", 422)
    if data["expiry_date"] <= clock.today():   # field 8.5
        raise DomainError("Термін дії паспорта має бути пізнішим за сьогоднішню дату", 422)
    if len(list_passports(db, user)) >= MAX_SAVED_PASSPORTS:
        raise DomainError(f"Можна зберегти не більше {MAX_SAVED_PASSPORTS} паспортів", 422)
    passport = SavedPassport(user_id=user.id,
                             last_name_lat=clean_latin_name(data["last_name_lat"]),
                             first_name_lat=clean_latin_name(data["first_name_lat"]),
                             passport_number=clean_passport_number(data["passport_number"]),
                             issuing_authority=authority, expiry_date=data["expiry_date"])
    db.add(passport)
    db.flush()
    return passport


def delete_passport(db: Session, user: User, passport_id: int) -> None:
    """Someone else's passport looks like a missing one (404)."""
    passport = db.scalar(select(SavedPassport).where(SavedPassport.id == passport_id,
                                                     SavedPassport.user_id == user.id))
    if passport is None:
        raise DomainError("Паспорт не знайдено", 404)
    db.delete(passport)
    db.flush()
