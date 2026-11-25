"""Administrator schemas: users, reference data, settings, audit log (ТЗ 4.5.8, form 4.6.4.1)."""
from datetime import datetime, time
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


# ---------- reference data (patch schemas forbid unknown fields, e.g. hotels.rating_avg)
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CountryIn(_Strict):
    iso_code: str
    name_uk: str
    name_en: str | None = None


class CountryPatch(_Strict):
    iso_code: str | None = None
    name_uk: str | None = None
    name_en: str | None = None


class CountryAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    iso_code: str
    name_uk: str
    name_en: str | None
    is_archived: bool


class CityIn(_Strict):
    country_id: int
    name_uk: str
    name_en: str | None = None
    iata_code: str | None = None


class CityPatch(_Strict):
    country_id: int | None = None
    name_uk: str | None = None
    name_en: str | None = None
    iata_code: str | None = None


class CityAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    country_id: int
    name_uk: str
    name_en: str | None
    iata_code: str | None
    is_archived: bool


class ResortIn(_Strict):
    country_id: int
    name_uk: str
    name_en: str | None = None


class ResortPatch(_Strict):
    country_id: int | None = None
    name_uk: str | None = None
    name_en: str | None = None


class ResortAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    country_id: int
    name_uk: str
    name_en: str | None
    is_archived: bool


class HotelFacts(_Strict):
    """Hotel facts for the tour page (form 4.6.4.2); all optional."""
    beach_line: int | None = Field(default=None, description="Лінія пляжу, 1–5")
    distance_to_beach_m: int | None = Field(default=None, description="До пляжу, м (0 — на пляжі)")
    distance_to_airport_km: int | None = Field(default=None, description="До аеропорту, км")
    check_in: time | None = Field(default=None, description="Заїзд з, HH:MM")
    check_out: time | None = Field(default=None, description="Виїзд до, HH:MM")
    amenities: list[str] = Field(default=[], description="Зручності, до 20 пунктів")
    room_types: list[str] = Field(default=[], description="Типи номерів, до 20 пунктів")


class HotelIn(HotelFacts):
    resort_id: int
    name: str
    stars: int | None = None
    description: str | None = None


class HotelPatch(_Strict):
    resort_id: int | None = None
    name: str | None = None
    stars: int | None = None
    description: str | None = None
    beach_line: int | None = None
    distance_to_beach_m: int | None = None
    distance_to_airport_km: int | None = None
    check_in: time | None = None
    check_out: time | None = None
    amenities: list[str] | None = None
    room_types: list[str] | None = None


class HotelAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resort_id: int
    name: str
    stars: int | None
    description: str | None
    beach_line: int | None
    distance_to_beach_m: int | None
    distance_to_airport_km: int | None
    check_in: time | None
    check_out: time | None
    amenities: list[str]
    room_types: list[str]
    rating_avg: Decimal | None          # read-only: from published reviews
    is_archived: bool


class ServiceTypeIn(_Strict):
    name_uk: str
    price_uah: Decimal
    is_default: bool = False


class ServiceTypePatch(_Strict):
    name_uk: str | None = None
    price_uah: Decimal | None = None
    is_default: bool | None = None


class ServiceTypeAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name_uk: str
    price_uah: Decimal
    is_default: bool
    is_archived: bool


class LanguageIn(_Strict):
    code: str
    name: str
    is_enabled: bool = True


class LanguagePatch(_Strict):
    name: str | None = None
    is_enabled: bool | None = None


class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    is_enabled: bool


# ---------- global settings (form 4.6.4.1)
class SettingsValues(BaseModel):
    eur_rate: Decimal                   # field 1, UAH per 1 EUR
    usd_rate: Decimal                   # field 2
    acquiring_percent: Decimal          # field 3
    booking_timeout_min: int            # field 4
    bank_transfer_hold_hours: int
    review_premoderation: bool
    system_email: str                   # field 6
    maintenance_mode: bool              # field 7
    support_phone: str                  # field 8, "" = not set
    support_email: str                  # field 9, "" = not set


class SettingChange(BaseModel):
    updated_at: datetime
    updated_by: int | None


class SettingsOut(SettingsValues):
    uah_rate: Decimal = Decimal("1")    # fixed
    changes: dict[str, SettingChange]   # when / by whom each value was last changed


class SettingsIn(_Strict):
    """Only the fields that are sent change. Ranges are checked by the service."""
    eur_rate: Decimal | None = None
    usd_rate: Decimal | None = None
    acquiring_percent: Decimal | None = None
    booking_timeout_min: int | None = None
    bank_transfer_hold_hours: int | None = None
    review_premoderation: bool | None = None
    system_email: str | None = None
    maintenance_mode: bool | None = None
    support_phone: str | None = Field(default=None, description="Порожній рядок прибирає телефон")
    support_email: str | None = Field(default=None, description="Порожній рядок прибирає e-mail")


class GatewayStatusOut(BaseModel):
    gateway: str                        # stripe | mock
    stripe_key_configured: bool
    stripe_key_mode: str | None         # test | live | None
    webhook_secret_configured: bool
    stripe_api_version: str
    how_to_change: str
