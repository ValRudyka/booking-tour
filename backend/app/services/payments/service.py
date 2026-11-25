"""Client payment (ТЗ 4.5.3 steps 7.2–9, 4.4 step 5) and handling of gateway events.

Card: a `payments` row (pending) + a Stripe Checkout Session; the order becomes `paid` only from a
verified webhook (never from the return page). Bank transfer: a pending row with the payment
details; the finance controller confirms it later (finance.py).

Idempotency without an events table: the payment row is locked (SELECT ... FOR UPDATE), so two
deliveries of one event are processed one after another, and payment states only move forward
(pending -> succeeded | failed): a repeated "completed" finds `succeeded` and does nothing, an
"expired" never touches a succeeded payment. Automatic refunds are recorded as rows and sent with
an idempotency key, so a retried event cannot refund twice.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import frontend_base_url, settings
from app.models import AuditLog, Order, Payment, User
from app.models.enums import (OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus)
from app.services import order_status
from app.services.app_settings import bank_transfer_hold_hours
from app.services.errors import DomainError
from app.services.orders import HoldExpired, expire_if_due
from app.services.payments.gateway import GatewayError, GatewayEvent, GatewaySession, PaymentGateway
from app.services.payments.sessions import close_open_sessions

logger = logging.getLogger("tour.payments")

CENT = Decimal("0.01")
# Stripe's minimum is 30 minutes after creation; a minute of margin for clock differences.
CHECKOUT_SESSION_LIFETIME = timedelta(minutes=31)
SUCCESS_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
FAILURE_EVENTS = {"checkout.session.expired", "checkout.session.async_payment_failed"}
# A pending refund finishes with refund.updated; any refund (even one that looked succeeded) can
# fail later with refund.failed (Stripe docs "Refunds", test card 4000000000005126).
REFUND_EVENTS = {"refund.updated", "refund.failed"}
ZERO_TOTAL_COMMENT = "Промокод покрив повну вартість — оплата не потрібна"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_minor(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_minor(amount: int) -> Decimal:
    return (Decimal(amount) / 100).quantize(CENT)


def lock_order(db: Session, order_id: int) -> Order:
    return db.scalar(select(Order).where(Order.id == order_id).with_for_update()
                     .execution_options(populate_existing=True))


def paid_total(db: Session, order: Order) -> Decimal:
    """Money kept for the order: succeeded payments minus refunds that were not rejected."""
    def total(kind: PaymentType, statuses: list[TransactionStatus]) -> Decimal:
        return db.scalar(select(func.coalesce(func.sum(Payment.paid_amount), 0))
                         .where(Payment.order_id == order.id, Payment.type == kind,
                                Payment.status.in_(statuses)))

    return (total(PaymentType.PAYMENT, [TransactionStatus.SUCCEEDED])
            - total(PaymentType.REFUND, [TransactionStatus.SUCCEEDED, TransactionStatus.PENDING]))


def amount_due(db: Session, order: Order) -> Decimal:
    return max(order.total_uah - paid_total(db, order), Decimal("0.00"))


def _pending(order: Order, method: PaymentMethod) -> list[Payment]:
    return [p for p in order.payments if p.type == PaymentType.PAYMENT and p.method == method
            and p.status == TransactionStatus.PENDING]


def bank_details(order: Order, payment: Payment) -> dict:
    return {"recipient": settings.bank_recipient, "iban": settings.bank_iban,
            "edrpou": settings.bank_edrpou, "bank_name": settings.bank_name,
            "amount_uah": payment.amount_uah, "purpose": payment.purpose,
            "pay_until": order.hold_expires_at}


def return_urls(order: Order) -> tuple[str, str]:
    """Where Stripe sends the client back: the frontend's pages (spec 05). The success page only
    waits for the webhook (it never marks anything paid); Stripe fills in {CHECKOUT_SESSION_ID}."""
    base = frontend_base_url()
    return (f"{base}/payment/success?order_id={order.id}&session_id={{CHECKOUT_SESSION_ID}}",
            f"{base}/payment/cancel?order_id={order.id}")


@dataclass
class PayResult:
    order: Order
    payment: Payment | None
    checkout_url: str | None = None
    bank: dict | None = None
    message: str | None = None


# ---------- the client starts a payment
def start_payment(db: Session, client: User, order: Order, method: PaymentMethod,
                  gateway: PaymentGateway) -> PayResult:
    order = lock_order(db, order.id)          # a double click cannot create two sessions
    if expire_if_due(db, order):
        raise HoldExpired()
    if order.status != OrderStatus.AWAITING_PAYMENT:
        raise DomainError("Оплатити можна лише замовлення в статусі «Очікує оплати»", 409)
    if order.total_uah == 0:                  # a promo code covered everything
        order_status.change_status(db, order, OrderStatus.PAID, None, ZERO_TOTAL_COMMENT)
        order.payment_status = PaymentStatus.PAID
        db.flush()
        return PayResult(order, None, message=ZERO_TOTAL_COMMENT)
    if method == PaymentMethod.CARD:
        return _pay_by_card(db, client, order, gateway)
    return _pay_by_transfer(db, client, order, gateway)


def _pay_by_card(db: Session, client: User, order: Order, gateway: PaymentGateway) -> PayResult:
    for payment in _pending(order, PaymentMethod.CARD):
        if not payment.stripe_session_id:
            continue
        try:
            session = gateway.retrieve_checkout_session(payment.stripe_session_id)
        except GatewayError:
            session = None
        if session is not None and session.status == "open":
            return PayResult(order, payment, checkout_url=session.url)   # reuse, no second session
        if session is not None and session.status == "complete":
            raise DomainError("Оплата вже обробляється — оновіть сторінку за хвилину", 409)
        payment.status = TransactionStatus.FAILED                     # expired or gone

    success_url, cancel_url = return_urls(order)
    try:
        with db.begin_nested():               # no payment row is kept if Stripe refuses
            payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                              status=TransactionStatus.PENDING, amount_uah=amount_due(db, order))
            db.add(payment)
            db.flush()
            session = gateway.create_checkout_session(
                payment_id=payment.id, order_id=order.id, order_number=order.number,
                amount_minor=to_minor(payment.amount_uah),
                description=f"Тур «{order.tour.title_uk}», замовлення {order.number}"[:250],
                customer_email=client.email, expires_at=utcnow() + CHECKOUT_SESSION_LIFETIME,
                success_url=success_url, cancel_url=cancel_url)
            payment.stripe_session_id = session.id
    except GatewayError as error:
        if error.code == "amount_too_small":
            raise DomainError("Сума замала для оплати карткою — оберіть банківський переказ", 409) from None
        logger.error("Gateway refused a session for order %s: %s", order.number, error)
        raise DomainError("Платіжний сервіс тимчасово недоступний, спробуйте пізніше", 502) from None
    db.refresh(order, ["payments"])
    return PayResult(order, payment, checkout_url=session.url)


def extend_hold(db: Session, order: Order, user: User | None, reason: str) -> None:
    """Bank transfers take days: hold the seats for bank_transfer_hold_hours from now."""
    new_hold = utcnow() + timedelta(hours=bank_transfer_hold_hours(db))
    if order.hold_expires_at is None or new_hold > order.hold_expires_at:
        db.add(AuditLog(user_id=user.id if user else None, entity="order", entity_id=str(order.id),
                        action="hold_extended",
                        old_value={"hold_expires_at": order.hold_expires_at.isoformat()
                                   if order.hold_expires_at else None},
                        new_value={"hold_expires_at": new_hold.isoformat(), "reason": reason}))
        order.hold_expires_at = new_hold


def _pay_by_transfer(db: Session, client: User, order: Order, gateway: PaymentGateway) -> PayResult:
    pending = _pending(order, PaymentMethod.BANK_TRANSFER)
    if pending:
        return PayResult(order, pending[-1], bank=bank_details(order, pending[-1]))
    first_transfer = not any(p.method == PaymentMethod.BANK_TRANSFER for p in order.payments)
    close_open_sessions(db, order, gateway)   # the client switched from card to transfer
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.BANK_TRANSFER,
                      status=TransactionStatus.PENDING, amount_uah=amount_due(db, order),
                      purpose=f"Оплата туру за замовленням {order.number}, "
                              f"{client.last_name} {client.first_name}"[:300])
    db.add(payment)
    if first_transfer:                        # extended once when the transfer is chosen
        extend_hold(db, order, client, "bank_transfer_chosen")
    db.flush()
    db.refresh(order, ["payments"])
    return PayResult(order, payment, bank=bank_details(order, payment))


# ---------- money received (card webhook or finance controller)
def apply_received_money(db: Session, order: Order, actor: User | None, comment: str) -> None:
    """After a payment succeeded: fully paid -> order `paid` (seats re-checked under the tour lock
    by change_status), otherwise `partially_paid`."""
    if paid_total(db, order) >= order.total_uah:
        order_status.change_status(db, order, OrderStatus.PAID, actor, comment)
        order.payment_status = PaymentStatus.PAID
    else:
        order.payment_status = PaymentStatus.PARTIALLY_PAID
    db.flush()


def _refund_status(status: str) -> TransactionStatus:
    if status == "succeeded":
        return TransactionStatus.SUCCEEDED
    if status in ("failed", "canceled"):
        return TransactionStatus.FAILED
    return TransactionStatus.PENDING


def refund_late_payment(db: Session, order: Order, payment: Payment, gateway: PaymentGateway,
                        reason: str) -> str:
    """CLAUDE.md rule: money that arrives for an order that can no longer be paid (cancelled, or the
    seats are gone) goes back automatically; the order status is not changed."""
    already = db.scalar(select(Payment).where(Payment.type == PaymentType.REFUND,
                                              Payment.refund_of_id == payment.id,
                                              Payment.status != TransactionStatus.FAILED))
    if already is not None:
        return "refunded"
    refund = gateway.refund(payment_intent=payment.stripe_payment_intent,
                            amount_minor=to_minor(payment.paid_amount),
                            idempotency_key=f"late-refund-{payment.id}",
                            metadata={"order_id": str(order.id), "payment_id": str(payment.id),
                                      "reason": "late_payment"})
    db.add(Payment(order_id=order.id, type=PaymentType.REFUND, method=PaymentMethod.CARD,
                   status=_refund_status(refund.status), amount_uah=payment.paid_amount,
                   paid_amount=payment.paid_amount, received_at=utcnow(), refund_of_id=payment.id,
                   stripe_payment_intent=payment.stripe_payment_intent, stripe_refund_id=refund.id,
                   controller_comment=f"Автоматичне повернення: {reason}"))
    db.flush()
    if paid_total(db, order) <= 0:            # nothing else was paid for this order
        order.payment_status = PaymentStatus.REFUNDED
    db.flush()
    logger.warning("Late payment %s for order %s refunded (%s): %s",
                   payment.id, order.number, refund.id, reason)
    return "refunded"


def _find_payment(db: Session, session: GatewaySession) -> Payment | None:
    payment_id = session.metadata.get("payment_id")
    query = select(Payment).where(Payment.stripe_session_id == session.id)
    if payment_id and payment_id.isdigit():
        query = select(Payment).where(Payment.id == int(payment_id),
                                      Payment.stripe_session_id == session.id)
    return db.scalar(query.with_for_update().execution_options(populate_existing=True))


def handle_event(db: Session, event: GatewayEvent, gateway: PaymentGateway) -> str:
    """Apply one gateway event. Returns what happened (for logs and tests)."""
    if event.type in REFUND_EVENTS and event.refund is not None:
        from app.services.payments.refunds import handle_refund_event   # refunds imports this module

        return handle_refund_event(db, event)
    if event.type not in SUCCESS_EVENTS | FAILURE_EVENTS or event.session is None:
        return "ignored"
    payment = _find_payment(db, event.session)
    if payment is None:
        logger.warning("Event %s for unknown session %s ignored", event.id, event.session.id)
        return "unknown_session"

    if event.type in FAILURE_EVENTS:
        if payment.status == TransactionStatus.PENDING:
            payment.status = TransactionStatus.FAILED
            db.flush()
            return "failed"
        return "ignored"                      # e.g. "expired" after "completed": keep the payment

    if event.session.payment_status != "paid":
        return "waiting"                      # delayed method: async_payment_succeeded comes later
    if payment.status == TransactionStatus.SUCCEEDED:
        return "duplicate"
    payment.status = TransactionStatus.SUCCEEDED
    payment.paid_amount = from_minor(event.session.amount_total or to_minor(payment.amount_uah))
    payment.received_at = utcnow()
    payment.stripe_payment_intent = event.session.payment_intent
    db.flush()

    order = lock_order(db, payment.order_id)
    if order.status != OrderStatus.AWAITING_PAYMENT:
        return refund_late_payment(db, order, payment, gateway, f"замовлення в статусі "
                                   f"«{order_status.STATUS_LABELS[order.status]}», оплата надійшла запізно")
    try:
        apply_received_money(db, order, None, "Оплату карткою отримано (Stripe)")
    except DomainError:                       # change_status found no free seats
        return refund_late_payment(db, order, payment, gateway, "немає вільних місць")
    return "paid" if order.status == OrderStatus.PAID else "partially_paid"


def payment_result(db: Session, session_id: str) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.stripe_session_id == session_id))
    if payment is None:
        raise DomainError("Платіж не знайдено", 404)
    return payment
