"""Close open Stripe Checkout Sessions of an order that will not be paid any more.

A Checkout Session lives at least 30 minutes (Stripe's minimum expires_at), but our seat hold is
booking_timeout_min (20). So whenever an unpaid order is cancelled (expiry job, expired hold
noticed on the next request, client's cancel) its open sessions are expired via the API
(POST /v1/checkout/sessions/{id}/expire). If that fails, or the client paid in the last second,
the payment still arrives through the webhook and is refunded automatically (service.py).
"""
import logging

from sqlalchemy.orm import Session

from app.models import Order
from app.models.enums import PaymentMethod, PaymentType, TransactionStatus
from app.services.payments.gateway import GatewayError, PaymentGateway, get_gateway

logger = logging.getLogger("tour.payments")


def close_open_sessions(db: Session, order: Order, gateway: PaymentGateway | None = None) -> None:
    gateway = gateway or get_gateway()
    for payment in order.payments:
        if (payment.type != PaymentType.PAYMENT or payment.method != PaymentMethod.CARD
                or payment.status != TransactionStatus.PENDING or not payment.stripe_session_id):
            continue
        try:
            if gateway.expire_checkout_session(payment.stripe_session_id):
                payment.status = TransactionStatus.FAILED
            elif gateway.retrieve_checkout_session(payment.stripe_session_id).status == "expired":
                payment.status = TransactionStatus.FAILED
            # "complete": the money is on its way; the webhook settles or refunds it.
        except GatewayError as error:
            logger.error("Could not expire session %s of order %s: %s",
                         payment.stripe_session_id, order.number, error)
    db.flush()
