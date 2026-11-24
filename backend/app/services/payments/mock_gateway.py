"""Gateway without network: used by the tests and for a demo without Stripe keys.

Sessions live in memory. The dev-only endpoints /api/payments/mock/... (enabled only when this
gateway is active) play the part of the Stripe payment page: they "pay" or "expire" a session and
feed the result to the same handlers the Stripe webhook uses. Calls are recorded for tests.
"""
import uuid

from app.config import settings
from app.services.payments.gateway import (GatewayError, GatewayEvent, GatewayRefund,
                                           GatewaySession, InvalidSignature, PaymentGateway)


class MockGateway(PaymentGateway):
    name = "mock"
    # Like Stripe for this account (~30 pence): smaller UAH amounts are rejected.
    MIN_AMOUNT_MINOR = 1700

    def __init__(self) -> None:
        self.sessions: dict[str, GatewaySession] = {}
        self.created: list[str] = []
        self.expire_calls: list[str] = []
        self.refunds: list[dict] = []
        self.fail_with: GatewayError | None = None   # tests: make the next call fail

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error

    def create_checkout_session(self, *, payment_id, order_id, order_number, amount_minor,
                                description, customer_email, expires_at, success_url, cancel_url):
        self._maybe_fail()
        if amount_minor < self.MIN_AMOUNT_MINOR:
            raise GatewayError("Amount too small", "amount_too_small")
        session_id = f"mock_cs_{payment_id}_{uuid.uuid4().hex[:8]}"
        session = GatewaySession(
            id=session_id, url=f"{settings.api_base_url}/api/payments/mock/{session_id}",
            status="open", payment_status="unpaid", payment_intent=None, amount_total=amount_minor,
            metadata={"order_id": str(order_id), "payment_id": str(payment_id),
                      "order_number": order_number})
        self.sessions[session_id] = session
        self.created.append(session_id)
        return session

    def retrieve_checkout_session(self, session_id: str) -> GatewaySession:
        self._maybe_fail()
        if session_id not in self.sessions:
            raise GatewayError(f"No such checkout.session: {session_id}", "resource_missing")
        return self.sessions[session_id]

    def expire_checkout_session(self, session_id: str) -> bool:
        self.expire_calls.append(session_id)
        self._maybe_fail()
        session = self.sessions.get(session_id)
        if session is None or session.status != "open":
            return False
        session.status = "expired"
        return True

    def refund(self, *, payment_intent, amount_minor, idempotency_key, metadata):
        self._maybe_fail()
        for done in self.refunds:            # same idempotency key -> same refund, like Stripe
            if done["idempotency_key"] == idempotency_key:
                return GatewayRefund(id=done["id"], status="succeeded")
        refund_id = f"mock_re_{len(self.refunds) + 1}"
        self.refunds.append({"id": refund_id, "payment_intent": payment_intent,
                             "amount_minor": amount_minor, "idempotency_key": idempotency_key,
                             "metadata": metadata})
        return GatewayRefund(id=refund_id, status="succeeded")

    def parse_webhook(self, payload: bytes, signature: str | None) -> GatewayEvent:
        raise InvalidSignature("The mock gateway does not receive webhooks")

    # ---------- what the Stripe payment page would do
    def complete(self, session_id: str) -> GatewayEvent:
        session = self.retrieve_checkout_session(session_id)
        session.status, session.payment_status = "complete", "paid"
        session.payment_intent = f"mock_pi_{session_id}"
        return GatewayEvent(id=f"mock_evt_{uuid.uuid4().hex[:8]}", type="checkout.session.completed",
                            session=session)

    def expire(self, session_id: str) -> GatewayEvent:
        session = self.retrieve_checkout_session(session_id)
        session.status = "expired"
        return GatewayEvent(id=f"mock_evt_{uuid.uuid4().hex[:8]}", type="checkout.session.expired",
                            session=session)
