"""Checkout schemas (ТЗ 4.5.3, form 4.6.1.2).

Pydantic checks only types; business rules (dates, categories, Latin names, passport validity,
seats, promo) are checked in services/orders.py so every message is in Ukrainian.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (CancelReason, ClientAction, Currency, MealPlan, OrderStatus, PaymentStatus,
                              TransportType)
from app.schemas.payments import BankDetailsOut, PaymentShortOut


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
    """Every field optional. `tourists` replaces the whole list (`[]` clears it, e.g. before
    changing the numbers of adults and children); `promo_code: null` removes the code;
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
    pnr: str | None                       # booking number, once confirmed
    reject_reason: str | None
    cancel_reason_code: CancelReason | None
    cancel_reason: str | None
    fpv_uah: Decimal | None               # ФПВ kept after a refund
    created_at: datetime
    # What the client may do now (services/order_actions.py): the cabinet shows only these.
    client_actions: list[ClientAction]


class OrderDetailOut(OrderOut):
    tourists: list[TouristOut]
    history: list[StatusHistoryOut]
    payments: list[PaymentShortOut] = []
    # Tour facts for the order page. Read from the tour row (not a snapshot of the order):
    # tours are never deleted, and /tours/{id} is linked only while tour_for_sale is true.
    tour_for_sale: bool
    country_name: str
    resort_name: str
    departure_city_name: str | None
    transport_type: TransportType
    meal_plan: MealPlan | None
    # A bank transfer the client chose and has not paid yet: the same details as POST /pay.
    pending_transfer: BankDetailsOut | None = None


class OrderWithPriceOut(OrderDetailOut):
    """Answer of create / update / confirm: the order plus the price just calculated."""
    price: PriceOut


class OrderDetailPriceOut(OrderDetailOut):
    """GET /orders/{id}: the order plus its itemised price, calculated on read and never saved.
    In «Оформлення» it is the current calculation; after confirm, the frozen total, discount and
    rate with the lines rebuilt from them. `price` is null when the lines cannot be rebuilt exactly
    (a tour or service price changed after confirm): `total_uah` is still the frozen amount."""
    price: PriceOut | None


class UploadLimitsOut(BaseModel):
    """File rules of a client form, from the backend settings (the client checks before sending,
    the server checks again, including the file contents)."""
    max_files: int
    max_file_mb: int
    file_types: list[str]      # extensions: "pdf", "jpg", "png"


class CancelRequestFormOut(BaseModel):
    """GET /orders/{id}/cancel-request: what form 4.6.1.3 needs from the server."""
    evidence: UploadLimitsOut
