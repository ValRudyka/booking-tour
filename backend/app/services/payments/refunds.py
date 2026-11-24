"""Refunds (ТЗ 4.5.6, form 4.6.3.1 field 9): the finance controller's queue and refund, and the
Stripe refund webhooks. Also the bookkeeping used by the manager's archive check.

Money of an order = rows in `payments`: succeeded payments in, refunds out. A refund row points at
the payment it returns money from (`refund_of_id`), so with several payments (partial bank
transfers + a card) we know how much of each one is still refundable.

Refund amount = succeeded payments − refunds already made or on their way − ФПВ. It is split over
the payments **newest first**: the newest payment is usually the card charge (the freshest one,
safest to refund through Stripe), and the ФПВ the company keeps stays on the oldest payment.
Card parts go through the Stripe Refund API, bank parts (and card parts Stripe could not refund,
`manual`) are recorded as transfers made by finance, with their details and receipt.

Idempotency: each Stripe part uses the key refund-<payment id>-<n>, n = refund rows of that payment
+ 1. If a later part fails after an earlier one was created in Stripe, the whole database change is
rolled back and finance repeats the same request: n is the same, so Stripe returns the refunds it
already made instead of making new ones. A failed refund keeps its row, so the next attempt gets a
new key. Stripe keeps keys at least 24 hours.

Order status: when every refund row has succeeded the refund is finished: «Очікує скасування»
-> «Скасовано» (seats back, via change_status), a rejected order stays «Відхилено», payment status
«Повернено» / «Повернено частково». A pending Stripe refund keeps the order where it is until
refund.updated arrives; refund.failed puts the order back into the queue.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import BinaryIO

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, Payment, User
from app.models.enums import OrderStatus as S
from app.models.enums import PaymentMethod, PaymentStatus, PaymentType, TransactionStatus
from app.services import notifications, private_files
from app.services.errors import DomainError
from app.services.order_status import STATUS_LABELS, change_status
from app.services.payments.gateway import GatewayError, GatewayEvent, PaymentGateway

logger = logging.getLogger("tour.payments")

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
LIVE_REFUND = (TransactionStatus.SUCCEEDED, TransactionStatus.PENDING)   # not failed
MAX_COMMENT = 2000
MAX_DETAILS = 300
CLOCK_SKEW = timedelta(minutes=5)
RETRY_MESSAGE = ("Платіжний сервіс не провів повернення. Частину коштів могло бути вже повернено — "
                 "повторіть той самий запит з тією самою сумою ФПВ: вже проведені частини "
                 "не будуть повернені вдруге")


# ---------- bookkeeping
def has_pending_refund(db: Session, order: Order) -> bool:
    return db.scalar(select(func.count()).where(
        Payment.order_id == order.id, Payment.type == PaymentType.REFUND,
        Payment.status == TransactionStatus.PENDING)) > 0


def _sum(db: Session, order: Order, kind: PaymentType, statuses) -> Decimal:
    return Decimal(db.scalar(select(func.coalesce(func.sum(Payment.paid_amount), 0))
                             .where(Payment.order_id == order.id, Payment.type == kind,
                                    Payment.status.in_(statuses)))).quantize(CENT)


def kept_money(db: Session, order: Order) -> Decimal:
    """Succeeded payments minus refunds that are done or on their way."""
    return (_sum(db, order, PaymentType.PAYMENT, [TransactionStatus.SUCCEEDED])
            - _sum(db, order, PaymentType.REFUND, LIVE_REFUND))


def refund_finished(db: Session, order: Order) -> bool:
    """Nothing more to return: no refund in progress and only the ФПВ (or nothing) is kept.
    Orders cancelled before payment hold no money and are finished at once."""
    if has_pending_refund(db, order):
        return False
    return kept_money(db, order) <= (order.fpv_uah or ZERO)


def _refund_status(status: str) -> TransactionStatus:
    if status == "succeeded":
        return TransactionStatus.SUCCEEDED
    if status in ("failed", "canceled"):
        return TransactionStatus.FAILED
    return TransactionStatus.PENDING          # pending, requires_action


# ---------- the queue «Повернення»
def _queue_filter(now: datetime):
    paid_in = (select(func.coalesce(func.sum(Payment.paid_amount), 0))
               .where(Payment.order_id == Order.id, Payment.type == PaymentType.PAYMENT,
                      Payment.status == TransactionStatus.SUCCEEDED).correlate(Order).scalar_subquery())
    paid_out = (select(func.coalesce(func.sum(Payment.paid_amount), 0))
                .where(Payment.order_id == Order.id, Payment.type == PaymentType.REFUND,
                       Payment.status.in_(LIVE_REFUND)).correlate(Order).scalar_subquery())
    pending = exists().where(Payment.order_id == Order.id, Payment.type == PaymentType.REFUND,
                             Payment.status == TransactionStatus.PENDING)
    owed = or_(paid_in - paid_out > func.coalesce(Order.fpv_uah, 0), pending)
    return or_(
        Order.status == S.CANCEL_REQUESTED,
        and_(Order.status.in_([S.REJECTED, S.CANCELLED]), owed),
        # Partly paid by transfer, and the client did not pay the rest in time (decided with the
        # owner): nobody else can cancel it, finance cancels it and returns the money.
        and_(Order.status == S.AWAITING_PAYMENT, Order.payment_status == PaymentStatus.PARTIALLY_PAID,
             Order.hold_expires_at <= now),
    )


def refund_queue(db: Session, page: int, page_size: int) -> tuple[list[Order], int]:
    query = select(Order).where(_queue_filter(datetime.now(timezone.utc)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(selectinload(Order.payments), selectinload(Order.client))
                       .order_by(Order.id).offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def queue_kind(db: Session, order: Order) -> str:
    if has_pending_refund(db, order):
        return "refund_pending"               # waiting for Stripe
    return {S.CANCEL_REQUESTED: "cancel_request", S.REJECTED: "rejected",
            S.CANCELLED: "refund_failed", S.AWAITING_PAYMENT: "unfinished_transfer"}.get(order.status, "other")


def money_summary(db: Session, order: Order) -> dict[str, Decimal]:
    return {"paid_uah": _sum(db, order, PaymentType.PAYMENT, [TransactionStatus.SUCCEEDED]),
            "refunded_uah": _sum(db, order, PaymentType.REFUND, [TransactionStatus.SUCCEEDED]),
            "pending_refund_uah": _sum(db, order, PaymentType.REFUND, [TransactionStatus.PENDING]),
            "kept_uah": kept_money(db, order)}


# ---------- the refund
@dataclass
class TransferDetails:
    """A refund made by bank transfer (form 4.6.3.1 fields 8, 7, 10)."""
    sent_at: datetime
    details: str
    statement: tuple[BinaryIO, str | None] | None = None


@dataclass
class RefundResult:
    order: Order
    rows: list[Payment]
    finished: bool


def _refundable(db: Session, payment: Payment) -> Decimal:
    returned = db.scalar(select(func.coalesce(func.sum(Payment.paid_amount), 0))
                         .where(Payment.refund_of_id == payment.id, Payment.status.in_(LIVE_REFUND)))
    return (payment.paid_amount - Decimal(returned)).quantize(CENT)


def _allocate(db: Session, order: Order, target: Decimal) -> list[tuple[Payment, Decimal]]:
    """Split `target` over the succeeded payments, newest first."""
    sources = db.scalars(select(Payment).where(
        Payment.order_id == order.id, Payment.type == PaymentType.PAYMENT,
        Payment.status == TransactionStatus.SUCCEEDED)
        .order_by(Payment.received_at.desc().nulls_last(), Payment.id.desc())).all()
    parts, left = [], target
    for payment in sources:
        if left <= 0:
            break
        take = min(_refundable(db, payment), left)
        if take > 0:
            parts.append((payment, take))
            left -= take
    if left > 0:                              # should not happen: kept_money says it is there
        raise DomainError("Суми платежів не вистачає для повернення — перевірте реєстр платежів", 409)
    return parts


def _check_request(db: Session, order: Order, fpv: Decimal) -> None:
    allowed = (S.CANCEL_REQUESTED, S.REJECTED, S.CANCELLED, S.AWAITING_PAYMENT)
    if order.status not in allowed or (order.status == S.AWAITING_PAYMENT
                                       and order.payment_status != PaymentStatus.PARTIALLY_PAID):
        raise DomainError(f"Для замовлення в статусі «{STATUS_LABELS[order.status]}» "
                          f"повернення не оформлюється", 409)
    if fpv < 0:
        raise DomainError("ФПВ не може бути від'ємним", 422)
    if order.status in (S.REJECTED, S.AWAITING_PAYMENT) and fpv != 0:
        raise DomainError("Тут ФПВ не утримується: повертається вся сплачена сума (ФПВ = 0)", 422)
    if order.status == S.CANCELLED and fpv != (order.fpv_uah or ZERO):
        raise DomainError(f"ФПВ для цього замовлення вже визначено: {order.fpv_uah or ZERO} грн", 422)
    if has_pending_refund(db, order):
        raise DomainError("Повернення вже обробляється — очікуємо підтвердження від Stripe", 409)


def refund_order(db: Session, controller: User, order_id: int, *, fpv: Decimal, comment: str | None,
                 transfer: TransferDetails | None, manual: bool, gateway: PaymentGateway) -> RefundResult:
    from app.services.payments.service import lock_order, to_minor, utcnow

    order = lock_order(db, order_id)          # a double click waits here and then sees the rows
    if order is None:
        raise DomainError("Замовлення не знайдено", 404)
    fpv = fpv.quantize(CENT)
    _check_request(db, order, fpv)
    kept = kept_money(db, order)
    if fpv > kept:
        raise DomainError(f"ФПВ більші за суму, що залишилась у компанії ({kept} грн)", 422)
    comment = (comment or "").strip() or None
    if fpv > 0 and comment is None:
        raise DomainError("При частковому поверненні коментар контролера обов'язковий", 422)
    if comment and len(comment) > MAX_COMMENT:
        raise DomainError(f"Коментар — не довше {MAX_COMMENT} символів", 422)
    target = kept - fpv
    if target == 0 and order.status in (S.REJECTED, S.CANCELLED):
        raise DomainError("Кошти за цим замовленням уже повернено", 409)

    parts = _allocate(db, order, target)
    by_stripe = [(p, a) for p, a in parts
                 if p.method == PaymentMethod.CARD and p.stripe_payment_intent and not manual]
    by_transfer = [(p, a) for p, a in parts if (p, a) not in by_stripe]
    if by_transfer:
        transfer = _check_transfer(transfer, utcnow())

    saved = None
    created: list[tuple[int, str]] = []       # (payment id, Stripe refund id) for the log
    try:
        with db.begin_nested():               # any failure: nothing of this refund is kept
            if by_transfer and transfer.statement is not None:
                saved = private_files.save_statement(f"refunds/{order.id}", *transfer.statement)
            rows = []
            for payment, amount in by_stripe:
                attempt = db.scalar(select(func.count()).where(Payment.refund_of_id == payment.id)) + 1
                try:
                    refund = gateway.refund(
                        payment_intent=payment.stripe_payment_intent, amount_minor=to_minor(amount),
                        idempotency_key=f"refund-{payment.id}-{attempt}",
                        metadata={"order_id": str(order.id), "payment_id": str(payment.id),
                                  "reason": "finance_refund"})
                except GatewayError as error:
                    _log_partial_failure(order, parts, created, error)
                    if error.code == "idempotency_error":
                        raise DomainError("Stripe уже має повернення цього платежу з іншою сумою. "
                                          "Повторіть запит з тією самою сумою ФПВ, що й першого разу",
                                          409) from None
                    raise DomainError(RETRY_MESSAGE, 502) from None
                created.append((payment.id, refund.id))
                rows.append(Payment(
                    order_id=order.id, type=PaymentType.REFUND, method=PaymentMethod.CARD,
                    status=_refund_status(refund.status), amount_uah=amount, paid_amount=amount,
                    received_at=utcnow(), refund_of_id=payment.id,
                    stripe_payment_intent=payment.stripe_payment_intent, stripe_refund_id=refund.id,
                    controller_comment=comment, confirmed_by=controller.id))
            for payment, amount in by_transfer:
                rows.append(Payment(
                    order_id=order.id, type=PaymentType.REFUND, method=PaymentMethod.BANK_TRANSFER,
                    status=TransactionStatus.SUCCEEDED, amount_uah=amount, paid_amount=amount,
                    received_at=transfer.sent_at, purpose=transfer.details, bank_statement_path=saved,
                    refund_of_id=payment.id, controller_comment=comment, confirmed_by=controller.id))
            db.add_all(rows)
            order.fpv_uah = fpv
            db.flush()
            finished = finish_if_complete(db, order, controller)
    except BaseException:
        private_files.remove(saved)
        raise
    db.refresh(order, ["payments"])
    return RefundResult(order, rows, finished)


def _check_transfer(transfer: TransferDetails | None, now: datetime) -> TransferDetails:
    if transfer is None or not (transfer.details or "").strip():
        raise DomainError("Частину коштів повертаємо банківським переказом: вкажіть дату та "
                          "реквізити переказу", 422)
    sent_at = transfer.sent_at
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    if sent_at > now + CLOCK_SKEW:
        raise DomainError("Дата переказу не може бути в майбутньому", 422)
    details = transfer.details.strip()
    if len(details) > MAX_DETAILS:
        raise DomainError(f"Реквізити переказу — не довше {MAX_DETAILS} символів", 422)
    return TransferDetails(sent_at, details, transfer.statement)


def _log_partial_failure(order: Order, parts, created: list[tuple[int, str]], error: GatewayError) -> None:
    payments = [p.id for p, _ in parts]
    if created:
        logger.warning("Refund of order %s stopped after a partial success: payments %s, Stripe "
                       "refunds already created %s; the database change was rolled back, the same "
                       "request must be repeated (same idempotency keys). Error: %s",
                       order.id, payments, created, error)
    else:
        logger.error("Refund of order %s failed (payments %s): %s", order.id, payments, error)


def finish_if_complete(db: Session, order: Order, actor: User | None) -> bool:
    """When all money but the ФПВ is back and nothing is pending: payment status, order status,
    the client's notification. Returns True if the refund is finished."""
    if not refund_finished(db, order):
        return False
    fpv = order.fpv_uah or ZERO
    # Orders this refund closes: a cancellation request, or a partly paid transfer order that
    # finance cancels (an awaiting order whose late card payment was refunded stays as it is).
    was_open = order.status == S.CANCEL_REQUESTED or (
        order.status == S.AWAITING_PAYMENT and order.payment_status == PaymentStatus.PARTIALLY_PAID)
    returned = _sum(db, order, PaymentType.REFUND, [TransactionStatus.SUCCEEDED])
    if returned > 0:
        order.payment_status = PaymentStatus.PARTIALLY_REFUNDED if fpv > 0 else PaymentStatus.REFUNDED
    text = f"Повернено {returned} грн" + (f", утримано фактично понесені витрати {fpv} грн" if fpv else "")
    if was_open:
        change_status(db, order, S.CANCELLED, actor, text)
    notifications.notify(db, order.client_id, f"Кошти за замовленням {order.number} повернено",
                         text + (". Бронювання скасовано." if was_open else "."), order)
    db.flush()
    return True


# ---------- refund webhooks: refund.updated / refund.failed
class RefundNotRecordedYet(GatewayError):
    """A refund we created whose row is not committed yet (the event came before our COMMIT, or
    the request was rolled back and will be repeated): answer 503 so Stripe sends it again."""


def handle_refund_event(db: Session, event: GatewayEvent) -> str:
    from app.services.payments.service import lock_order

    refund = event.refund
    row = db.scalar(select(Payment).where(Payment.stripe_refund_id == refund.id)
                    .with_for_update().execution_options(populate_existing=True))
    if row is None:
        if refund.metadata.get("payment_id"):
            raise RefundNotRecordedYet(f"Refund {refund.id} is not recorded yet")
        return "unknown_refund"               # e.g. made by hand in the Dashboard
    new = _refund_status(refund.status)
    if row.status == new or row.status == TransactionStatus.FAILED or new == TransactionStatus.PENDING:
        return "duplicate" if row.status == new else "ignored"   # states only move forward
    row.status = new                          # pending -> succeeded | failed, succeeded -> failed
    db.flush()
    order = lock_order(db, row.order_id)
    if new == TransactionStatus.SUCCEEDED:
        finish_if_complete(db, order, None)
        return "refund_succeeded"

    # A failed refund: the money is with us again (Stripe docs: pay the customer another way).
    returned = _sum(db, order, PaymentType.REFUND, [TransactionStatus.SUCCEEDED])
    if returned > 0:
        order.payment_status = PaymentStatus.PARTIALLY_REFUNDED
    elif order.payment_status in (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED):
        order.payment_status = PaymentStatus.PAID
    notifications.notify_finance(db, order, f"Повернення за замовленням {order.number} не вдалося",
                                 f"Stripe не зміг повернути {row.paid_amount} грн (повернення "
                                 f"{refund.id}). Поверніть кошти іншим способом — замовлення знову "
                                 f"в черзі повернень.")
    db.flush()
    logger.warning("Refund %s of order %s failed", refund.id, order.number)
    return "refund_failed"
