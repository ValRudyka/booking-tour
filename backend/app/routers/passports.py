"""Saved passports of the client for «Заповнити з профілю» (ТЗ form 4.6.1.1, field 8)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.passports import PassportIn, PassportOut
from app.services import passports as passport_service
from app.services.errors import DomainError

router = APIRouter(prefix="/me/passports", tags=["me: passports"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


@router.get("", response_model=list[PassportOut], summary="Мої збережені паспорти")
def list_passports(db: DbSession, client: Client):
    return passport_service.list_passports(db, client)


@router.post("", response_model=PassportOut, status_code=status.HTTP_201_CREATED,
             summary="Зберегти паспорт")
def add_passport(data: PassportIn, db: DbSession, client: Client):
    try:
        passport = passport_service.add_passport(db, client, data.model_dump())
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    db.commit()
    return passport


@router.delete("/{passport_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити паспорт")
def delete_passport(passport_id: int, db: DbSession, client: Client):
    try:
        passport_service.delete_passport(db, client, passport_id)
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    db.commit()
