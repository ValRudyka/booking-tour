"""Saved passports of the client for «Заповнити з профілю» (ТЗ form 4.6.1.1, field 8)."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.passports import PassportIn, PassportOut
from app.services import passports as passport_service
from app.services.errors import DomainError

router = APIRouter(prefix="/me/passports", tags=["me: passports"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


def _fail(error: DomainError) -> NoReturn:
    """A rule about one form field answers like FastAPI's 422 with its `loc` (type
    "profile_rule": msg is a Ukrainian text for the client), as in the personal account."""
    if error.loc is not None:
        raise HTTPException(status_code=error.status_code, detail=[
            {"loc": list(error.loc), "msg": error.message, "type": "profile_rule"}]) from None
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


@router.get("", response_model=list[PassportOut], summary="Мої збережені паспорти")
def list_passports(db: DbSession, client: Client):
    return passport_service.list_passports(db, client)


@router.post("", response_model=PassportOut, status_code=status.HTTP_201_CREATED,
             summary="Зберегти паспорт")
def add_passport(data: PassportIn, db: DbSession, client: Client):
    try:
        passport = passport_service.add_passport(db, client, data.model_dump())
    except DomainError as error:
        _fail(error)
    db.commit()
    return passport


@router.put("/{passport_id}", response_model=PassportOut, summary="Змінити збережений паспорт")
def update_passport(passport_id: int, data: PassportIn, db: DbSession, client: Client):
    try:
        passport = passport_service.update_passport(db, client, passport_id, data.model_dump())
    except DomainError as error:
        _fail(error)
    db.commit()
    return passport


@router.delete("/{passport_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити паспорт")
def delete_passport(passport_id: int, db: DbSession, client: Client):
    try:
        passport_service.delete_passport(db, client, passport_id)
    except DomainError as error:
        _fail(error)
    db.commit()
