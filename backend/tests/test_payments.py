"""Card payments: «Оплатити», the Stripe webhook, late-payment refunds, closing sessions.

The mock gateway is used for the client flow; webhook tests use the real StripeGateway signature
check with a test secret, and its network methods are replaced by recorders (no network).
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Order, Payment, Tour
from app.models.enums import (OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus, UserRole)
from app.services.order_expiry import expire_orders
from app.services.payments.gateway import GatewayError, GatewayRefund, set_gateway
from app.services.payments.stripe_gateway import StripeGateway
from tests.factories import (headers_for, make_active_tour, make_order, make_user,
                             stripe_signature)

NOW = datetime.now(timezone.utc)
SECRET = "whsec_test_secret"
WEBHOOK = "/api/payments/stripe/webhook"


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)                       # 10 seats


@pytest.fixture()
def order(db, customer, tour):
    """An order waiting for payment: 2 adults, 77 500.00 UAH, hold for 20 more minutes."""
    return make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT, adults=2,
                      total_uah=Decimal("77500.00"), hold_expires_at=NOW + timedelta(minutes=20))


def pay(client, headers, order_id, method="card"):
    return client.post(f"/api/orders/{order_id}/pay", json={"method": method}, headers=headers)


def payments_of(db, order_id, kind=PaymentType.PAYMENT):
    return db.scalars(select(Payment).where(Payment.order_id == order_id, Payment.type == kind)
                      .order_by(Payment.id)).all()


# ---------- «Оплатити» карткою (mock gateway)
def test_pay_creates_one_pending_payment_and_reuses_the_session(client, db, customer_headers,
                                                                 order, gateway):
    first = pay(client, customer_headers, order.id)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["checkout_url"].startswith(f"{settings.api_base_url}/api/payments/mock/mock_cs_")
    assert body["payment"]["status"] == "pending" and body["payment"]["amount_uah"] == "77500.00"
    again = pay(client, customer_headers, order.id).json()
    assert again["checkout_url"] == body["checkout_url"]
    assert again["payment"]["id"] == body["payment"]["id"]
    assert len(gateway.created) == 1
    [payment] = payments_of(db, order.id)
    assert (payment.method, payment.status, payment.stripe_session_id) == (
        PaymentMethod.CARD, TransactionStatus.PENDING, gateway.created[0])


def test_new_session_after_the_old_one_expired(client, db, customer_headers, order, gateway):
    old = pay(client, customer_headers, order.id).json()["payment"]["id"]
    client.post(f"/api/payments/mock/{gateway.created[0]}/expire")
    new = pay(client, customer_headers, order.id).json()["payment"]["id"]
    assert new != old
    assert [p.status for p in payments_of(db, order.id)] == [TransactionStatus.FAILED,
                                                             TransactionStatus.PENDING]


def test_pay_wrong_owner_status_and_expired_hold(client, db, customer, customer_headers, tour, order):
    assert pay(client, headers_for(make_user(db)), order.id).status_code == 404
    in_checkout = make_order(db, customer, tour, hold_expires_at=NOW + timedelta(minutes=5))
    response = pay(client, customer_headers, in_checkout.id)
    assert response.status_code == 409
    assert "«Очікує оплати»" in response.json()["detail"]
    order.hold_expires_at = NOW - timedelta(seconds=1)
    db.flush()
    response = pay(client, customer_headers, order.id)
    assert response.status_code == 409
    assert "Час на оформлення замовлення минув" in response.json()["detail"]
    db.expire_all()
    assert db.get(Order, order.id).status == OrderStatus.CANCELLED


def test_pay_access(client, db, order):
    assert client.post(f"/api/orders/{order.id}/pay", json={}).status_code == 401
    for role in (UserRole.MANAGER, UserRole.FINANCE, UserRole.ADMIN):
        assert pay(client, headers_for(make_user(db, role=role)), order.id).status_code == 403


def test_zero_total_is_paid_at_once(client, db, customer_headers, order):
    order.total_uah = Decimal("0.00")
    db.flush()
    body = pay(client, customer_headers, order.id).json()
    assert (body["order_status"], body["payment_status"], body["payment"]) == ("paid", "paid", None)
    db.expire_all()
    paid = db.get(Order, order.id)
    assert paid.history[-1].changed_by is None
    assert "Промокод покрив повну вартість" in paid.history[-1].comment
    assert db.get(Tour, paid.tour_id).seats_sold == 2


def test_amount_below_stripe_minimum(client, db, customer_headers, order):
    order.total_uah = Decimal("10.00")
    db.flush()
    response = pay(client, customer_headers, order.id)
    assert response.status_code == 409
    assert "оберіть банківський переказ" in response.json()["detail"]
    assert payments_of(db, order.id) == []


def test_gateway_failure_leaves_no_payment(client, db, customer_headers, order, gateway):
    gateway.fail_with = GatewayError("connection refused")
    response = pay(client, customer_headers, order.id)
    assert response.status_code == 502
    assert payments_of(db, order.id) == []


def test_mock_payment_end_to_end(client, db, customer, customer_headers, order, gateway):
    pay(client, customer_headers, order.id)
    session_id = gateway.created[0]
    assert "Тестова оплата" in client.get(f"/api/payments/mock/{session_id}").text
    assert client.post(f"/api/payments/mock/{session_id}/succeed").json()["result"] == "paid"
    db.expire_all()
    paid = db.get(Order, order.id)
    assert (paid.status, paid.payment_status) == (OrderStatus.PAID, PaymentStatus.PAID)
    assert db.get(Tour, paid.tour_id).seats_sold == 2
    result = client.get("/api/payments/result", params={"session_id": session_id}).json()
    assert (result["order_status"], result["payment_status"]) == ("paid", "paid")
    assert result["message"].startswith("Оплату отримано")
    detail = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert [(p["method"], p["status"]) for p in detail["payments"]] == [("card", "succeeded")]


def test_mock_page_returns_to_the_frontend_like_stripe(client, db, customer_headers, order, gateway):
    """Demo without Stripe keys: the mock page's buttons send the browser to the frontend pages."""
    pay(client, customer_headers, order.id)
    session_id = gateway.created[0]
    base = "http://localhost:5173"                       # FRONTEND_URL empty, APP_ENV=test
    page = client.get(f"/api/payments/mock/{session_id}").text
    assert f'href="{base}/payment/cancel?order_id={order.id}"' in page
    response = client.post(f"/api/payments/mock/{session_id}/succeed",
                           params={"return_to_site": 1}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"{base}/payment/success?order_id={order.id}&session_id={session_id}")
    db.expire_all()
    assert db.get(Order, order.id).status == OrderStatus.PAID     # paid by the event, not the URL


def test_mock_expire_returns_to_the_cancel_page(client, customer_headers, order, gateway):
    pay(client, customer_headers, order.id)
    response = client.post(f"/api/payments/mock/{gateway.created[0]}/expire",
                           params={"return_to_site": 1}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/payment/cancel?order_id={order.id}")


def test_result_page(client, customer_headers, order, gateway):
    assert client.get("/api/payments/result", params={"session_id": "cs_nope"}).status_code == 404
    pay(client, customer_headers, order.id)
    body = client.get("/api/payments/result",
                      params={"session_id": gateway.created[0], "cancelled": "true"}).json()
    assert body["message"].startswith("Оплату не завершено")


# ---------- Stripe webhook (real signature check, network methods recorded)
class RecordingStripe(StripeGateway):
    def __init__(self):
        super().__init__("sk_test_dummy_not_used", SECRET, settings.stripe_api_version)
        self.refunds, self.expired = [], []
        self.refund_error: GatewayError | None = None

    def refund(self, **kwargs):
        if self.refund_error:
            raise self.refund_error
        self.refunds.append(kwargs)
        return GatewayRefund(id=f"re_test_{len(self.refunds)}", status="succeeded")

    def expire_checkout_session(self, session_id):
        self.expired.append(session_id)
        return True

    def retrieve_checkout_session(self, session_id):
        raise GatewayError("not used in these tests")

    def create_checkout_session(self, **kwargs):
        raise AssertionError("tests must not create real Stripe sessions")


@pytest.fixture()
def stripe_gw():
    fake = RecordingStripe()
    set_gateway(fake)
    return fake


@pytest.fixture()
def card_payment(db, order):
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                      status=TransactionStatus.PENDING, amount_uah=order.total_uah,
                      stripe_session_id=f"cs_test_{order.id}")
    db.add(payment)
    db.flush()
    return payment


def event(payment, type_="checkout.session.completed", payment_status="paid", event_id="evt_1"):
    return {"id": event_id, "object": "event", "type": type_, "data": {"object": {
        "id": payment.stripe_session_id, "object": "checkout.session",
        "status": "expired" if type_.endswith("expired") else "complete",
        "payment_status": payment_status, "payment_intent": "pi_test_1",
        "amount_total": int(payment.amount_uah * 100),
        "metadata": {"order_id": str(payment.order_id), "payment_id": str(payment.id)}}}}


def send(client, body, secret=SECRET, header=None):
    payload = json.dumps(body).encode()
    signature = header if header is not None else stripe_signature(payload, secret)
    return client.post(WEBHOOK, content=payload, headers={"Stripe-Signature": signature,
                                                          "Content-Type": "application/json"})


def test_webhook_rejects_bad_signatures(client, stripe_gw, card_payment):
    assert send(client, event(card_payment), secret="whsec_other").status_code == 400
    assert send(client, event(card_payment), header="t=1,v1=abc").status_code == 400
    response = client.post(WEBHOOK, content=b"{}")
    assert response.status_code == 400
    assert response.json()["detail"] == "Невірний підпис вебхука"
    assert card_payment.status == TransactionStatus.PENDING


def test_completed_marks_order_paid(client, db, stripe_gw, order, card_payment):
    response = send(client, event(card_payment))
    assert response.status_code == 200, response.text
    assert response.json()["result"] == "paid"
    db.expire_all()
    payment, paid = db.get(Payment, card_payment.id), db.get(Order, order.id)
    assert (payment.status, payment.paid_amount, payment.stripe_payment_intent) == (
        TransactionStatus.SUCCEEDED, Decimal("77500.00"), "pi_test_1")
    assert payment.received_at is not None
    assert (paid.status, paid.payment_status) == (OrderStatus.PAID, PaymentStatus.PAID)
    assert db.get(Tour, paid.tour_id).seats_sold == 2
    assert (paid.history[-1].new_status, paid.history[-1].changed_by) == ("paid", None)


def test_duplicate_event_changes_nothing(client, db, stripe_gw, order, card_payment):
    send(client, event(card_payment))
    history_rows = len(db.get(Order, order.id).history)
    assert send(client, event(card_payment)).json()["result"] == "duplicate"
    db.expire_all()
    assert db.get(Tour, order.tour_id).seats_sold == 2
    assert len(db.get(Order, order.id).history) == history_rows


def test_expired_event(client, db, stripe_gw, order, card_payment):
    assert send(client, event(card_payment, "checkout.session.expired")).json()["result"] == "failed"
    db.expire_all()
    assert db.get(Payment, card_payment.id).status == TransactionStatus.FAILED
    assert db.get(Order, order.id).status == OrderStatus.AWAITING_PAYMENT


def test_expired_after_completed_does_not_touch_paid_order(client, db, stripe_gw, order, card_payment):
    send(client, event(card_payment))
    assert send(client, event(card_payment, "checkout.session.expired",
                              event_id="evt_2")).json()["result"] == "ignored"
    db.expire_all()
    assert db.get(Payment, card_payment.id).status == TransactionStatus.SUCCEEDED
    assert db.get(Order, order.id).status == OrderStatus.PAID


def test_async_payment_events(client, db, stripe_gw, order, card_payment):
    # Completed while a delayed method is still processing: wait, change nothing.
    assert send(client, event(card_payment, payment_status="unpaid")).json()["result"] == "waiting"
    assert db.get(Payment, card_payment.id).status == TransactionStatus.PENDING
    assert send(client, event(card_payment, "checkout.session.async_payment_succeeded",
                              event_id="evt_2")).json()["result"] == "paid"


def test_async_payment_failed(client, db, stripe_gw, card_payment):
    assert send(client, event(card_payment, "checkout.session.async_payment_failed",
                              payment_status="unpaid")).json()["result"] == "failed"


def test_late_payment_for_cancelled_order_is_refunded(client, db, stripe_gw, order, card_payment):
    from app.services.order_status import change_status

    change_status(db, order, OrderStatus.CANCELLED, None, "Час на оплату минув")
    assert send(client, event(card_payment)).json()["result"] == "refunded"
    assert send(client, event(card_payment)).json()["result"] == "duplicate"   # no second refund
    assert len(stripe_gw.refunds) == 1
    assert stripe_gw.refunds[0]["payment_intent"] == "pi_test_1"
    assert stripe_gw.refunds[0]["amount_minor"] == 7750000
    assert stripe_gw.refunds[0]["idempotency_key"] == f"late-refund-{card_payment.id}"
    db.expire_all()
    [refund] = payments_of(db, order.id, PaymentType.REFUND)
    assert (refund.status, refund.amount_uah, refund.stripe_refund_id) == (
        TransactionStatus.SUCCEEDED, Decimal("77500.00"), "re_test_1")
    assert "Автоматичне повернення" in refund.controller_comment
    cancelled = db.get(Order, order.id)
    assert (cancelled.status, cancelled.payment_status) == (OrderStatus.CANCELLED, PaymentStatus.REFUNDED)
    assert db.get(Tour, order.tour_id).seats_sold == 0


def test_last_seat_taken_meanwhile_is_refunded(client, db, stripe_gw, customer, tour, order,
                                               card_payment):
    """The hold ran out while the client was paying, someone else took the seats."""
    tour.seats_total = 3
    order.hold_expires_at = NOW - timedelta(minutes=1)
    make_order(db, make_user(db), tour, status=OrderStatus.CHECKOUT, adults=2,
               hold_expires_at=NOW + timedelta(minutes=10))
    db.flush()
    assert send(client, event(card_payment)).json()["result"] == "refunded"
    db.expire_all()
    left = db.get(Tour, tour.id)
    assert left.seats_sold == 0 and left.seats_sold <= left.seats_total
    assert db.get(Order, order.id).status == OrderStatus.AWAITING_PAYMENT     # status kept
    assert len(stripe_gw.refunds) == 1


def test_refund_failure_is_retried_later(client, db, stripe_gw, order, card_payment):
    from app.services.order_status import change_status

    change_status(db, order, OrderStatus.CANCELLED, None)
    stripe_gw.refund_error = GatewayError("Stripe is down")
    assert send(client, event(card_payment)).status_code == 503
    db.expire_all()
    assert db.get(Payment, card_payment.id).status == TransactionStatus.PENDING   # rolled back
    stripe_gw.refund_error = None
    assert send(client, event(card_payment)).json()["result"] == "refunded"


def test_unknown_session_and_other_events_are_acknowledged(client, stripe_gw, card_payment):
    other = event(card_payment)
    other["data"]["object"]["id"] = "cs_someone_else"
    assert send(client, other).json()["result"] == "unknown_session"
    charge = {"id": "evt_9", "object": "event", "type": "charge.refunded",
              "data": {"object": {"id": "ch_1", "object": "charge"}}}
    assert send(client, charge).json()["result"] == "ignored"


def test_mock_endpoints_are_off_with_stripe(client, stripe_gw):
    assert client.get("/api/payments/mock/mock_cs_1").status_code == 404
    assert client.post("/api/payments/mock/mock_cs_1/succeed").status_code == 404


# ---------- closing Stripe sessions when an unpaid order is cancelled
def test_expire_orders_expires_the_stripe_session(db, stripe_gw, order, card_payment):
    order.hold_expires_at = NOW - timedelta(seconds=1)
    db.flush()
    assert expire_orders(db) == 1
    assert stripe_gw.expired == [card_payment.stripe_session_id]
    assert card_payment.status == TransactionStatus.FAILED
    assert order.status == OrderStatus.CANCELLED


def test_gateway_error_does_not_stop_the_expiry(db, gateway, order, card_payment):
    gateway.fail_with = GatewayError("Stripe is down")
    order.hold_expires_at = NOW - timedelta(seconds=1)
    db.flush()
    assert expire_orders(db) == 1
    assert gateway.expire_calls == [card_payment.stripe_session_id]
    assert order.status == OrderStatus.CANCELLED
    assert card_payment.status == TransactionStatus.PENDING   # a late payment will be refunded


def test_client_cancel_expires_the_session(client, db, customer_headers, order, gateway):
    pay(client, customer_headers, order.id)
    assert client.post(f"/api/orders/{order.id}/cancel", headers=customer_headers).status_code == 200
    assert gateway.expire_calls == gateway.created
    assert payments_of(db, order.id)[0].status == TransactionStatus.FAILED


def test_expired_hold_noticed_on_pay_expires_the_session(client, db, customer_headers, order, gateway):
    pay(client, customer_headers, order.id)
    db.get(Order, order.id).hold_expires_at = NOW - timedelta(seconds=1)
    db.flush()
    assert pay(client, customer_headers, order.id).status_code == 409
    assert gateway.expire_calls == gateway.created
