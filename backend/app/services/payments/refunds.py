"""Refund bookkeeping shared by the manager (archive check) and the finance controller.

Money of an order = rows in `payments`: succeeded payments in, refunds out. A refund row points
at the payment it returns money from (`refund_of_id`), so with several payments (partial bank
transfers + a card) we know how much of each one is still refundable.
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, Payment
from app.models.enums import PaymentType, TransactionStatus

ZERO = Decimal("0.00")
LIVE_REFUND = (TransactionStatus.SUCCEEDED, TransactionStatus.PENDING)   # not failed


def has_pending_refund(db: Session, order: Order) -> bool:
    return db.scalar(select(func.count()).where(
        Payment.order_id == order.id, Payment.type == PaymentType.REFUND,
        Payment.status == TransactionStatus.PENDING)) > 0


def kept_money(db: Session, order: Order) -> Decimal:
    """Succeeded payments minus refunds that are done or on their way."""
    def total(kind: PaymentType, statuses) -> Decimal:
        return db.scalar(select(func.coalesce(func.sum(Payment.paid_amount), 0))
                         .where(Payment.order_id == order.id, Payment.type == kind,
                                Payment.status.in_(statuses)))

    return Decimal(total(PaymentType.PAYMENT, [TransactionStatus.SUCCEEDED])
                   - total(PaymentType.REFUND, LIVE_REFUND)).quantize(Decimal("0.01"))


def refund_finished(db: Session, order: Order) -> bool:
    """Nothing more to return: no refund in progress and only the ФПВ (or nothing) is kept.
    Orders cancelled before payment hold no money and are finished at once."""
    if has_pending_refund(db, order):
        return False
    return kept_money(db, order) <= (order.fpv_uah or ZERO)
