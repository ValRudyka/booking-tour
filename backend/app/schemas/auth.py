"""Request/response schemas for registration, login and the personal account (form 4.6.1.1)."""
import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole

PHONE_RE = re.compile(r"^\+\d{10,15}$")


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s\-()]", "", value)
    if not PHONE_RE.match(phone):
        raise ValueError("Телефон у міжнародному форматі, наприклад +380501234567")
    return phone


class ProfileFields(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    birth_date: date | None = None
    citizenship_id: int | None = None

    @field_validator("last_name", "first_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class RegisterRequest(ProfileFields):
    phone: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    consent: bool = Field(description="Згода на обробку персональних даних (обов'язкова)")
    # Form 4.6.1.1, fields 6–7 and scenario 4.5.1 step 3: required at registration (18+ is checked
    # in services/users.py). The columns stay nullable: staff created by the admin may have none.
    birth_date: date = Field(description="Дата народження; клієнт має бути повнолітнім (18+)")
    citizenship_id: int = Field(description="Громадянство (id з довідника країн)")

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("consent")
    @classmethod
    def check_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Потрібна згода на обробку персональних даних")
        return value


class ProfileUpdate(BaseModel):
    """Fields the client may change in the personal account. All optional."""
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    birth_date: date | None = None
    citizenship_id: int | None = None
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    email: str
    role: UserRole
    last_name: str
    first_name: str
    birth_date: date | None
    citizenship_id: int | None
    loyalty_points: int
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
