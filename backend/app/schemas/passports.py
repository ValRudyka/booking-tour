"""Saved passports (ТЗ form 4.6.1.1, field 8). Rules are checked in services/passports.py."""
from datetime import date

from pydantic import BaseModel, ConfigDict


class PassportIn(BaseModel):
    last_name_lat: str
    first_name_lat: str
    passport_number: str
    issuing_authority: str | None = None   # 4-digit code, optional
    expiry_date: date
    birth_date: date                       # for the checkout autofill (form 4.6.1.2, field 3.6)


class PassportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_name_lat: str
    first_name_lat: str
    passport_number: str
    issuing_authority: str | None
    expiry_date: date
    birth_date: date | None                # None: saved before birth dates were kept
