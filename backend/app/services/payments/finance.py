"""Finance controller: payments register and manual confirmation of bank transfers
(ТЗ 4.4 step 5, scenario 4.5.6 steps 1–2, 4–5, form 4.6.3.1). Refunds are feature/order-processing.

Every money movement is its own row. A transfer for less than expected closes the pending row
with the amount received and opens a new pending row for the remainder, so each incoming transfer
keeps its own amount, date, purpose and statement.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, Payment, User
from app.models.enums import (OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus)
from app.services import clock, private_files
from app.services.errors import DomainError
from app.services.order_status import STATUS_LABELS
from app.services.payments.service import (CENT, apply_received_money, extend_hold, lock_order,
                                           utcnow)

MAX_PURPOSE = 300
MAX_COMMENT = 2000
CLOCK_SKEW = timedelta(minutes=5)


def list_payments(db: Session, *, status: TransactionStatus | None, method: PaymentMethod | None,
                  kind: PaymentType | None, date_from: date | None, date_to: date | None,
                  order_number: str | None, page: int, page_size: int) -> tuple[list[Payment], int]:
    """Register «Фінанси / Транзакції»; dates filter by when the payment row was created."""
    query = select(Payment).join(Order, Payment.order_id == Order.id)
    if status is not None:
        query = query.where(Payment.status == status)
    if method is not None:
        query = query.where(Payment.method == method)
    if kind is not None:
        query = query.where(Payment.type == kind)
    # Dates are Kyiv days (the controller's calendar), not UTC days.
    if date_from is not None:
        query = query.where(Payment.created_at >= clock.day_start(date_from))
    if date_to is not None:
        query = query.where(Payment.created_at < clock.day_start(date_to + timedelta(days=1)))
    if order_number:
        query = query.where(Order.number.icontains(order_number.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Payment.created_at.desc(), Payment.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_payment(db: Session, payment_id: int, lock: bool = False) -> Payment:
    query = select(Payment).where(Payment.id == payment_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    payment = db.scalar(query)
    if payment is None:
        raise DomainError("Платіж не знайдено", 404)
    return payment


def confirm_transfer(db: Session, controller: User, payment_id: int, *, paid_amount: Decimal,
                     received_at: datetime, purpose: str, comment: str | None,
                     statement: tuple[BinaryIO, str | None] | None) -> Payment:
    """Form 4.6.3.1, fields 4, 7, 8, 10, 11. Full amount -> order paid (seats re-checked);
    less -> «Сплачено частково», a pending row for the rest, the seat hold extended again."""
    payment = get_payment(db, payment_id, lock=True)
    if payment.type != PaymentType.PAYMENT or payment.method != PaymentMethod.BANK_TRANSFER:
        raise DomainError("Вручну підтверджується лише банківський переказ", 409)
    if payment.status != TransactionStatus.PENDING:
        raise DomainError("Цей платіж уже оброблено", 409)
    order = lock_order(db, payment.order_id)
    if order.status != OrderStatus.AWAITING_PAYMENT:
        raise DomainError(f"Замовлення в статусі «{STATUS_LABELS[order.status]}» — "
                          f"зарахувати оплату не можна", 409)

    paid_amount = paid_amount.quantize(CENT)
    if paid_amount <= 0:
        raise DomainError("Фактично сплачена сума має бути більшою за 0", 422)
    if paid_amount > payment.amount_uah:
        raise DomainError(f"Сума більша за очікувану ({payment.amount_uah} грн)", 422)
    if received_at.tzinfo is None:            # the form sends no zone: take it as UTC
        received_at = received_at.replace(tzinfo=timezone.utc)
    if received_at > utcnow() + CLOCK_SKEW:
        raise DomainError("Дата надходження не може бути в майбутньому", 422)
    purpose = (purpose or "").strip()
    if not purpose:
        raise DomainError("Вкажіть призначення платежу з банківської виписки", 422)
    if len(purpose) > MAX_PURPOSE:
        raise DomainError(f"Призначення платежу — не довше {MAX_PURPOSE} символів", 422)
    comment = (comment or "").strip() or None
    if comment and len(comment) > MAX_COMMENT:
        raise DomainError(f"Коментар — не довше {MAX_COMMENT} символів", 422)

    saved = private_files.save_statement(payment.id, *statement) if statement else None
    try:
        expected_purpose = payment.purpose
        remainder = payment.amount_uah - paid_amount
        payment.status = TransactionStatus.SUCCEEDED
        payment.paid_amount, payment.received_at = paid_amount, received_at
        payment.purpose, payment.controller_comment = purpose, comment
        payment.bank_statement_path, payment.confirmed_by = saved, controller.id
        if remainder > 0:
            db.add(Payment(order_id=order.id, type=PaymentType.PAYMENT,
                           method=PaymentMethod.BANK_TRANSFER, status=TransactionStatus.PENDING,
                           amount_uah=remainder, purpose=expected_purpose))
        db.flush()
        apply_received_money(db, order, controller, "Банківський переказ підтверджено")
        if order.payment_status == PaymentStatus.PARTIALLY_PAID:
            extend_hold(db, order, controller, "partial_payment")
        db.flush()
    except BaseException:
        private_files.remove(saved)          # no orphan statement if the change is refused
        raise
    return payment


def statement_file(db: Session, payment_id: int) -> tuple[str, str, str]:
    """(absolute path, download name, media type) of the payment's bank statement."""
    payment = get_payment(db, payment_id)
    if not payment.bank_statement_path:
        raise DomainError("До платежу не додано виписку", 404)
    path = private_files.absolute(payment.bank_statement_path)
    if not path.exists():
        raise DomainError("Файл виписки не знайдено", 404)
    ext = path.suffix.lstrip(".")
    return str(path), f"statement-{payment.order.number}-{payment.id}.{ext}", private_files.MEDIA_TYPES[ext]
