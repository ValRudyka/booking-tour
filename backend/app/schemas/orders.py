"""Checkout schemas (ТЗ 4.5.3, form 4.6.1.2).

Pydantic checks only types; business rules (dates, categories, Latin names, passport validity,
seats, promo) are checked in services/orders.py so every message is in Ukrainian.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import Currency, OrderStatus, PaymentStatus
from app.schemas.payments import PaymentShortOut


# ---------- input
class TouristBirth(BaseModel):
    birth_date: date


class TouristIn(TouristBirth):
    """Form 4.6.1.2, fields 3.2–3.6 (a copy of the passport, not a link to a saved one)."""
    last_name_lat: str
    first_name_lat: str
    passport_number: str
    passport_expiry: date


class QuoteRequest(BaseModel):
    tour_id: int
    start_date: date
    adults: int
    children: int = 0
    tourists: list[TouristBirth] | None = None   # optional: checks adult/child categories
    insurance_type_id: int | None = None          # None = default («Базове»)
    transfer_type_id: int | None = None           # None = default («Груповий»)
    promo_code: str | None = None


class OrderCreate(BaseModel):
    """«Забронювати»: the client picks the tour, date and number of tourists; passport data
    may come now or later with PATCH, but all of it is required at confirm."""
    tour_id: int
    start_date: date
    adults: int
    children: int = 0
    tourists: list[TouristIn] | None = None
    insurance_type_id: int | None = None
    transfer_type_id: int | None = None
    promo_code: str | None = None
    wishes: str | None = None


class OrderUpdate(BaseModel):
    """Every field optional. `tourists` replaces the whole list; `promo_code: null` removes the code;
    `insurance_type_id` / `transfer_type_id: null` go back to the default option."""
    adults: int | None = None
    children: int | None = None
    tourists: list[TouristIn] | None = None
    insurance_type_id: int | None = None
    transfer_type_id: int | None = None
    promo_code: str | None = None
    wishes: str | None = None


class OrderConfirm(BaseModel):
    accept_offer: bool = False   # form 4.6.1.2, field 9 — must be true


# ---------- output
class PriceOut(BaseModel):
    """Itemised price, form 4.6.1.2 field 8."""
    model_config = ConfigDict(from_attributes=True)

    adults: int
    children: int
    currency: Currency
    base_price: Decimal
    child_price: Decimal
    rate: Decimal
    tour_uah: Decimal
    insurance_id: int | None
    insurance_name: str | None
    insurance_per_tourist_uah: Decimal
    insurance_uah: Decimal
    transfer_id: int | None
    transfer_name: str | None
    transfer_uah: Decimal
    subtotal_uah: Decimal
    promo_code: str | None
    discount_uah: Decimal
    total_uah: Decimal


class TouristOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_name_lat: str
    first_name_lat: str
    birth_date: date
    passport_number: str
    passport_expiry: date


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_status: OrderStatus | None
    new_status: OrderStatus
    changed_by: int | None       # NULL = the System
    comment: str | None
    changed_at: datetime


class OrderOut(BaseModel):
    id: int
    number: str
    status: OrderStatus
    payment_status: PaymentStatus
    tour_id: int
    tour_title_uk: str
    hotel_name: str
    start_date: date
    end_date: date
    adults: int
    children: int
    insurance_type_id: int | None
    transfer_type_id: int | None
    promo_code: str | None
    wishes: str | None
    total_uah: Decimal
    discount_uah: Decimal
    rate_used: Decimal
    hold_expires_at: datetime | None
    offer_accepted_at: datetime | None
    created_at: datetime


class OrderDetailOut(OrderOut):
    tourists: list[TouristOut]
    history: list[StatusHistoryOut]
    payments: list[PaymentShortOut] = []


class OrderWithPriceOut(OrderDetailOut):
    """Answer of create / update / confirm: the order plus the price just calculated."""
    price: PriceOut
