"""Manager: promo codes (ТЗ 4.3 «створювати, редагувати та деактивувати промокоди», form 4.6.2.3).

- code: 4–20 Latin letters and digits, stored in upper case, unique;
- percent 1–100 or a fixed amount in UAH > 0; optional minimum order and usage limit;
- valid_to later than valid_from; the active flag;
- usage is read-only: used_count = orders that hold a use of the code now (the counter the
  checkout limit uses, services/promo.py), paid_count = orders paid with it (form field 8);
- a code that any order has used cannot be deleted (only deactivated), and its text cannot be
  changed — placed orders keep their frozen discount and refer to it.
Every change is written to the audit log.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, PromoCode, User
from app.models.enums import DiscountType, PaymentStatus
from app.services.audit import audit, changed, snapshot
from app.services.errors import DomainError
from app.services.promo import normalize_code, usage_count

CODE_RE = re.compile(r"^[A-Z0-9]{4,20}$")
FIELDS = ("code", "discount_type", "discount_value", "min_order_uah", "valid_from", "valid_to",
          "usage_limit", "is_active")
PAID = (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)
MAX_UAH = Decimal("1000000")


def paid_count(db: Session, promo: PromoCode) -> int:
    return db.scalar(select(func.count()).where(Order.promo_code_id == promo.id, Order.payment_status.in_(PAID)))


def ever_used(db: Session, promo: PromoCode) -> bool:
    return db.scalar(select(func.count()).where(Order.promo_code_id == promo.id)) > 0


def counts(db: Session, promo: PromoCode) -> dict[str, int]:
    return {"used_count": usage_count(db, promo), "paid_count": paid_count(db, promo)}


def list_codes(db: Session, *, is_active: bool | None, q: str | None, page: int,
               page_size: int) -> tuple[list[PromoCode], int]:
    query = select(PromoCode)
    if is_active is not None:
        query = query.where(PromoCode.is_active.is_(is_active))
    if q and q.strip():
        query = query.where(PromoCode.code.icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(PromoCode.valid_to.desc(), PromoCode.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_code(db: Session, promo_id: int, lock: bool = False) -> PromoCode:
    query = select(PromoCode).where(PromoCode.id == promo_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    promo = db.scalar(query)
    if promo is None:
        raise DomainError("Промокод не знайдено", 404)
    return promo


def _money(value: Any, label: str, low: Decimal, high: Decimal, strict_low: bool = False) -> Decimal:
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise DomainError(f"«{label}»: потрібне число", 422) from None
    if (number <= low if strict_low else number < low) or number > high:
        raise DomainError(f"«{label}»: {'більше' if strict_low else 'від'} {low} до {high}", 422)
    return number


def _validate(db: Session, values: dict[str, Any], promo: PromoCode | None) -> dict[str, Any]:
    """`values` = the full form after applying the changes."""
    code = normalize_code(values.get("code") or "")
    if not CODE_RE.match(code):
        raise DomainError("Код промокоду — 4–20 латинських літер і цифр, наприклад SUMMER2027", 422)
    clash = db.scalar(select(PromoCode.id).where(PromoCode.code == code))
    if clash is not None and (promo is None or clash != promo.id):
        raise DomainError(f"Промокод {code} уже існує", 409)
    kind = values.get("discount_type")
    if kind not in (DiscountType.PERCENT, DiscountType.FIXED):
        raise DomainError("Тип знижки — відсоткова або фіксована (грн)", 422)
    if kind == DiscountType.PERCENT:
        value = _money(values.get("discount_value"), "Розмір знижки, %", Decimal("1"), Decimal("100"))
    else:
        value = _money(values.get("discount_value"), "Розмір знижки, грн", Decimal("0"), MAX_UAH, strict_low=True)
    min_order = values.get("min_order_uah")
    if min_order is not None:
        min_order = _money(min_order, "Мінімальна сума замовлення", Decimal("0"), MAX_UAH)
    valid_from, valid_to = values.get("valid_from"), values.get("valid_to")
    if not isinstance(valid_from, date) or not isinstance(valid_to, date):
        raise DomainError("Вкажіть дати початку і завершення дії", 422)
    if valid_to <= valid_from:
        raise DomainError("Дата завершення дії має бути пізнішою за дату початку", 422)
    limit = values.get("usage_limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise DomainError("Ліміт використань — ціле число від 1 (або порожньо — без обмежень)", 422)
    return {"code": code, "discount_type": kind, "discount_value": value, "min_order_uah": min_order,
            "valid_from": valid_from, "valid_to": valid_to, "usage_limit": limit,
            "is_active": bool(values.get("is_active", True))}


def create_code(db: Session, manager: User, data: dict[str, Any]) -> PromoCode:
    promo = PromoCode(**_validate(db, data, None), created_by=manager.id)
    db.add(promo)
    db.flush()
    audit(db, manager, "promo_code", promo.id, "created", new=snapshot(promo, FIELDS))
    return promo


def update_code(db: Session, manager: User, promo_id: int, changes: dict[str, Any]) -> PromoCode:
    promo = get_code(db, promo_id, lock=True)
    before = snapshot(promo, FIELDS)
    merged = before | changes
    if "code" in changes and normalize_code(changes["code"] or "") != promo.code and ever_used(db, promo):
        raise DomainError("Промокод уже використано в замовленнях — його текст не змінюється "
                          "(можна змінити інші поля або деактивувати)", 409)
    for field, value in _validate(db, merged, promo).items():
        setattr(promo, field, value)
    db.flush()
    old, new = changed(before, snapshot(promo, FIELDS))
    if new:
        audit(db, manager, "promo_code", promo.id,
              "deactivated" if new.get("is_active") is False and len(new) == 1 else "updated", old, new)
    return promo


def delete_code(db: Session, manager: User, promo_id: int) -> None:
    promo = get_code(db, promo_id, lock=True)
    if ever_used(db, promo):
        raise DomainError("Промокод уже використано в замовленнях — його не можна видалити, "
                          "лише деактивувати", 409)
    old = snapshot(promo, FIELDS)
    db.delete(promo)
    db.flush()
    audit(db, manager, "promo_code", promo_id, "deleted", old=old)

