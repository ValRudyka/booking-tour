"""Saved foreign passports for checkout autofill (ТЗ form 4.6.1.1, field 8) and the passport rules
shared with the checkout (form 4.6.1.2, fields 3.2–3.4)."""
import re
from collections.abc import Sequence
from datetime import date
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


EARLIEST_BIRTH_DATE = date(1900, 1, 1)


def _field_error(message: str, field: str, status_code: int = 422) -> DomainError:
    """A rule about one field of the form: the router answers it with this `loc`."""
    return DomainError(message, status_code, loc=("body", field))


def _clean(db: Session, user: User, data: dict[str, Any], passport_id: int | None) -> dict[str, Any]:
    """Fields 8.1–8.5 of form 4.6.1.1 plus the birth date (form 4.6.1.2, field 3.6). Each error
    names its field. The same passport number twice in the client's list is refused."""
    cleaned: dict[str, Any] = {}
    for field, clean in (("last_name_lat", clean_latin_name), ("first_name_lat", clean_latin_name),
                         ("passport_number", clean_passport_number)):
        try:
            cleaned[field] = clean(data[field])
        except DomainError as error:
            raise _field_error(error.message, field) from None
    authority = (data.get("issuing_authority") or "").strip() or None
    if authority is not None and not AUTHORITY_CODE.match(authority):
        raise _field_error("Орган, що видав, — 4-значний цифровий код", "issuing_authority")
    if data["expiry_date"] <= clock.today():   # field 8.5
        raise _field_error("Термін дії паспорта має бути пізнішим за сьогоднішню дату", "expiry_date")
    birth_date = data["birth_date"]
    if birth_date > clock.today():
        raise _field_error("Дата народження не може бути пізнішою за сьогоднішню", "birth_date")
    if birth_date < EARLIEST_BIRTH_DATE:
        raise _field_error("Перевірте дату народження", "birth_date")
    duplicate = select(SavedPassport.id).where(SavedPassport.user_id == user.id,
                                               SavedPassport.passport_number == cleaned["passport_number"])
    if passport_id is not None:
        duplicate = duplicate.where(SavedPassport.id != passport_id)
    if db.scalar(duplicate) is not None:
        raise _field_error("Паспорт з таким номером уже збережено", "passport_number", 409)
    return cleaned | {"issuing_authority": authority, "expiry_date": data["expiry_date"],
                      "birth_date": birth_date}


def add_passport(db: Session, user: User, data: dict[str, Any]) -> SavedPassport:
    if len(list_passports(db, user)) >= MAX_SAVED_PASSPORTS:
        raise DomainError(f"Можна зберегти не більше {MAX_SAVED_PASSPORTS} паспортів", 422)
    passport = SavedPassport(user_id=user.id, **_clean(db, user, data, None))
    db.add(passport)
    db.flush()
    return passport


def _own(db: Session, user: User, passport_id: int) -> SavedPassport:
    """Someone else's passport looks like a missing one (404)."""
    passport = db.scalar(select(SavedPassport).where(SavedPassport.id == passport_id,
                                                     SavedPassport.user_id == user.id))
    if passport is None:
        raise DomainError("Паспорт не знайдено", 404)
    return passport


def update_passport(db: Session, user: User, passport_id: int, data: dict[str, Any]) -> SavedPassport:
    """All fields at once (PUT), with the same rules as a new passport."""
    passport = _own(db, user, passport_id)
    for field, value in _clean(db, user, data, passport_id).items():
        setattr(passport, field, value)
    db.flush()
    return passport


def delete_passport(db: Session, user: User, passport_id: int) -> None:
    db.delete(_own(db, user, passport_id))
    db.flush()
