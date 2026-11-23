"""Promo codes at checkout (ТЗ 4.5.3 step 5, form 4.6.2.3). Read-only use: the admin manages them.

A code is accepted when it is active, today is within valid_from..valid_to, the order amount
(before the discount) reaches min_order_uah and the usage limit is not used up.

Usage = orders with this code that still count: not cancelled/rejected and not an expired hold.
Unpaid orders count too (unlike form 4.6.2.3 field 8, "paid orders"), otherwise more clients
than the limit could apply the code at the same time. The promo row is locked while an order
takes a use, so the last use cannot go to two orders.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Order, PromoCode
from app.models.enums import OrderStatus
from app.services.errors import DomainError
from app.services.seats import HOLDING_STATUSES


def normalize_code(code: str) -> str:
    return code.strip().upper()


def usage_count(db: Session, promo: PromoCode, exclude_order_id: int | None = None) -> int:
    query = (select(func.count()).select_from(Order)
             .where(Order.promo_code_id == promo.id,
                    Order.status.not_in([OrderStatus.CANCELLED, OrderStatus.REJECTED]),
                    or_(Order.status.not_in(HOLDING_STATUSES),
                        Order.hold_expires_at > datetime.now(timezone.utc))))
    if exclude_order_id is not None:
        query = query.where(Order.id != exclude_order_id)
    return db.scalar(query)


def find_valid_promo(db: Session, code: str, subtotal: Decimal, today: date, *,
                     exclude_order_id: int | None = None, lock: bool = False) -> PromoCode:
    """Return the promo code or raise a DomainError (422) that says exactly what is wrong."""
    query = select(PromoCode).where(PromoCode.code == normalize_code(code))
    if lock:
        query = query.with_for_update()
    promo = db.scalar(query)
    if promo is None:
        raise DomainError("Промокод не знайдено", 422)
    if not promo.is_active:
        raise DomainError("Промокод неактивний", 422)
    if today < promo.valid_from:
        raise DomainError(f"Промокод діє з {promo.valid_from:%d.%m.%Y}", 422)
    if today > promo.valid_to:
        raise DomainError(f"Термін дії промокоду минув {promo.valid_to:%d.%m.%Y}", 422)
    if promo.min_order_uah is not None and subtotal < promo.min_order_uah:
        raise DomainError(f"Промокод діє для замовлень від {promo.min_order_uah:.2f} грн", 422)
    if promo.usage_limit is not None and usage_count(db, promo, exclude_order_id) >= promo.usage_limit:
        raise DomainError("Ліміт використань промокоду вичерпано", 422)
    return promo
