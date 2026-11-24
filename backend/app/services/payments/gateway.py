"""Payment gateway interface. The rest of the app talks only to PaymentGateway, so Stripe can be
replaced by the mock (tests, demo without keys) or by another acquirer later.

PAYMENT_GATEWAY=stripe|mock chooses the implementation; when it is empty, Stripe is used only if
STRIPE_SECRET_KEY is set. Tests always run with the mock (tests/conftest.py).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings


@dataclass
class GatewaySession:
    """The part of a Stripe Checkout Session the app needs."""
    id: str
    url: str | None
    status: str                    # open | complete | expired
    payment_status: str            # unpaid | paid | no_payment_required
    payment_intent: str | None
    amount_total: int | None       # minor units (kopecks)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class GatewayRefund:
    id: str
    status: str                    # pending | requires_action | succeeded | failed | canceled
    amount_minor: int | None = None
    payment_intent: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class GatewayEvent:
    id: str
    type: str
    session: GatewaySession | None  # None for events that are not about a Checkout Session
    refund: GatewayRefund | None = None   # refund.updated / refund.failed


class GatewayError(Exception):
    """The gateway is unreachable or rejected the request (code = Stripe error code, if any;
    "idempotency_error" = the key was already used with other parameters)."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class InvalidSignature(Exception):
    """The webhook request is not signed by the gateway."""


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    def create_checkout_session(self, *, payment_id: int, order_id: int, order_number: str,
                                amount_minor: int, description: str, customer_email: str | None,
                                expires_at: datetime, success_url: str,
                                cancel_url: str) -> GatewaySession: ...

    @abstractmethod
    def retrieve_checkout_session(self, session_id: str) -> GatewaySession: ...

    @abstractmethod
    def expire_checkout_session(self, session_id: str) -> bool:
        """Close an open session so it can no longer be paid. False if it was not open."""

    @abstractmethod
    def refund(self, *, payment_intent: str, amount_minor: int, idempotency_key: str,
               metadata: dict[str, str]) -> GatewayRefund: ...

    @abstractmethod
    def parse_webhook(self, payload: bytes, signature: str | None) -> GatewayEvent:
        """Verify the signature and parse the event; raises InvalidSignature."""


def gateway_name() -> str:
    name = settings.payment_gateway.strip().lower() or ("stripe" if settings.stripe_secret_key else "mock")
    if name not in ("stripe", "mock"):
        raise ValueError("PAYMENT_GATEWAY must be 'stripe' or 'mock'")
    return name


_gateway: PaymentGateway | None = None


def get_gateway() -> PaymentGateway:
    """The configured gateway (one instance per process). Also a FastAPI dependency."""
    global _gateway
    if _gateway is None:
        if gateway_name() == "stripe":
            from app.services.payments.stripe_gateway import StripeGateway

            if not settings.stripe_secret_key:
                raise RuntimeError("PAYMENT_GATEWAY=stripe needs STRIPE_SECRET_KEY")
            _gateway = StripeGateway(settings.stripe_secret_key, settings.stripe_webhook_secret,
                                     settings.stripe_api_version)
        else:
            from app.services.payments.mock_gateway import MockGateway

            _gateway = MockGateway()
    return _gateway


def set_gateway(gateway: PaymentGateway | None) -> None:
    """Replace the process-wide gateway (tests); None = build it again from the settings."""
    global _gateway
    _gateway = gateway
