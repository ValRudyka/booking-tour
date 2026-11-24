"""Administrator schemas: users, reference data, settings, audit log (ТЗ 4.5.8, form 4.6.4.1)."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.auth import UserOut, normalize_phone


# ---------- users
class AdminUserOut(UserOut):
    updated_at: datetime


class StaffCreate(BaseModel):
    role: UserRole
    phone: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Початковий пароль")
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("last_name", "first_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    is_active: bool | None = None
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


# ---------- audit log
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None          # NULL = the System
    entity: str
    entity_id: str
    action: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime
