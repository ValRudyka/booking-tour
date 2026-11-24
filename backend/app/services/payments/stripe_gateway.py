"""Stripe Checkout (test mode) behind the PaymentGateway interface.

Uses StripeClient (the module-level `stripe.api_key` pattern is deprecated), API version pinned in
settings. Payment methods are not listed: Stripe shows the methods enabled in the Dashboard
(dynamic payment methods). Idempotency keys make retries of the same request safe.
"""
import logging
from datetime import datetime
from typing import Any

import stripe
from stripe import StripeClient

from app.services.payments.gateway import (GatewayError, GatewayEvent, GatewayRefund,
                                           GatewaySession, InvalidSignature, PaymentGateway)

logger = logging.getLogger("tour.payments")


def _plain(obj: Any) -> dict[str, Any]:
    """Since stripe-python v13 a StripeObject is not a dict any more: convert it first."""
    return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)


def _session(obj: Any) -> GatewaySession:
    data = _plain(obj)
    intent = data.get("payment_intent")
    if isinstance(intent, dict):                              # expanded PaymentIntent
        intent = intent.get("id")
    return GatewaySession(id=data["id"], url=data.get("url"), status=data.get("status"),
                          payment_status=data.get("payment_status"), payment_intent=intent,
                          amount_total=data.get("amount_total"),
                          metadata={k: str(v) for k, v in (data.get("metadata") or {}).items()})


class StripeGateway(PaymentGateway):
    name = "stripe"

    def __init__(self, api_key: str, webhook_secret: str, api_version: str):
        self._client = StripeClient(api_key, stripe_version=api_version, max_network_retries=2)
        self._webhook_secret = webhook_secret

    def create_checkout_session(self, *, payment_id, order_id, order_number, amount_minor,
                                description, customer_email, expires_at, success_url, cancel_url):
        metadata = {"order_id": str(order_id), "payment_id": str(payment_id),
                    "order_number": order_number}
        params: dict[str, Any] = {
            "mode": "payment",
            "currency": "uah",
            "line_items": [{"quantity": 1, "price_data": {
                "currency": "uah", "unit_amount": amount_minor,
                "product_data": {"name": description}}}],
            "client_reference_id": order_number,
            "metadata": metadata,
            "payment_intent_data": {"metadata": metadata},   # also visible on the payment itself
            "expires_at": int(expires_at.timestamp()),
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        if customer_email:
            params["customer_email"] = customer_email
        try:
            session = self._client.v1.checkout.sessions.create(
                params=params, options={"idempotency_key": f"checkout-payment-{payment_id}"})
        except stripe.StripeError as error:
            raise GatewayError(error.user_message or str(error), getattr(error, "code", None)) from error
        return _session(session)

    def retrieve_checkout_session(self, session_id: str) -> GatewaySession:
        try:
            return _session(self._client.v1.checkout.sessions.retrieve(session_id))
        except stripe.StripeError as error:
            raise GatewayError(str(error), getattr(error, "code", None)) from error

    def expire_checkout_session(self, session_id: str) -> bool:
        try:
            self._client.v1.checkout.sessions.expire(session_id)
            return True
        except stripe.InvalidRequestError as error:
            # Only open sessions can be expired; complete/expired ones answer 400.
            logger.info("Stripe session %s was not expired: %s", session_id, error.user_message)
            return False
        except stripe.StripeError as error:
            raise GatewayError(str(error), getattr(error, "code", None)) from error

    def refund(self, *, payment_intent, amount_minor, idempotency_key, metadata):
        try:
            refund = self._client.v1.refunds.create(
                params={"payment_intent": payment_intent, "amount": amount_minor, "metadata": metadata},
                options={"idempotency_key": idempotency_key})
        except stripe.StripeError as error:
            raise GatewayError(str(error), getattr(error, "code", None)) from error
        return GatewayRefund(id=refund.id, status=refund.status)

    def parse_webhook(self, payload: bytes, signature: str | None) -> GatewayEvent:
        if not self._webhook_secret:
            raise InvalidSignature("STRIPE_WEBHOOK_SECRET is not set")
        try:
            event = self._client.construct_event(payload, signature, self._webhook_secret)
        except (stripe.SignatureVerificationError, ValueError) as error:
            raise InvalidSignature(str(error)) from error
        obj = event.data.object
        session = _session(obj) if _plain(obj).get("object") == "checkout.session" else None
        return GatewayEvent(id=event.id, type=event.type, session=session)
