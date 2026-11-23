"""Order price (ТЗ form 4.6.1.2, field 8):

    (base_price × adults + child_price × children) × rate
      + insurance price × tourists + transfer price − promo discount

child_price NULL = base price; a child is under 12 on the tour start date. All maths in Decimal,
each money amount rounded to 0.01 with ROUND_HALF_UP (the usual "round half up" for money,
not Python's default banker's rounding).
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models import InsuranceType, PromoCode, Tour, TransferType
from app.models.enums import Currency, DiscountType

CENT = Decimal("0.01")
CHILD_AGE_LIMIT = 12  # under 12 on the start date = child (form 4.6.1.2, field 3.6)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def age_on(birth_date: date, day: date) -> int:
    """Full years on `day`. Tuple comparison handles birthdays not yet reached (and 29 Feb)."""
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def is_child(birth_date: date, start_date: date) -> bool:
    return age_on(birth_date, start_date) < CHILD_AGE_LIMIT


def promo_discount(promo: PromoCode, subtotal: Decimal) -> Decimal:
    """Percent of the subtotal (tour + insurance + transfer) or a fixed UAH amount;
    never more than the subtotal, so the total cannot go below zero."""
    if promo.discount_type == DiscountType.PERCENT:
        discount = money(subtotal * promo.discount_value / 100)
    else:
        discount = money(promo.discount_value)
    return min(discount, subtotal)


@dataclass
class PriceBreakdown:
    adults: int
    children: int
    currency: Currency
    base_price: Decimal          # per adult, tour currency
    child_price: Decimal         # per child, tour currency (= base price if not set)
    rate: Decimal                # UAH for 1 unit of the tour currency
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


def calculate(tour: Tour, rate: Decimal, adults: int, children: int,
              insurance: InsuranceType | None, transfer: TransferType | None,
              promo: PromoCode | None = None) -> PriceBreakdown:
    """Pure calculation; the promo code must already be validated (services/promo.py)."""
    child_price = tour.child_price if tour.child_price is not None else tour.base_price
    tour_uah = money((tour.base_price * adults + child_price * children) * rate)
    per_tourist = insurance.price_uah if insurance else Decimal(0)
    insurance_uah = money(per_tourist * (adults + children))
    transfer_uah = money(transfer.price_uah) if transfer else Decimal("0.00")
    subtotal = tour_uah + insurance_uah + transfer_uah
    discount = promo_discount(promo, subtotal) if promo else Decimal("0.00")
    return PriceBreakdown(
        adults=adults, children=children, currency=tour.currency, base_price=money(tour.base_price),
        child_price=money(child_price), rate=rate, tour_uah=tour_uah,
        insurance_id=insurance.id if insurance else None,
        insurance_name=insurance.name_uk if insurance else None,
        insurance_per_tourist_uah=money(per_tourist), insurance_uah=insurance_uah,
        transfer_id=transfer.id if transfer else None,
        transfer_name=transfer.name_uk if transfer else None, transfer_uah=transfer_uah,
        subtotal_uah=subtotal, promo_code=promo.code if promo else None, discount_uah=discount,
        total_uah=subtotal - discount,
    )
