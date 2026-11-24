"""Stripe refund webhooks: refund.updated finishes a pending refund, refund.failed puts the order
back in the finance queue. Events are signed and checked by the real StripeGateway."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Notification, Order, Payment, Tour
from app.models.enums import (OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus, UserRole)
from app.services.payments import service as payment_service
from app.services.payments.gateway import GatewayEvent, GatewaySession, set_gateway
from app.services.payments.stripe_gateway import StripeGateway
from tests.factories import headers_for, make_active_tour, make_order, make_paid_order, make_user, stripe_signature

NOW = datetime.now(timezone.utc)
SECRET = "whsec_refund_test"
WEBHOOK = "/api/payments/stripe/webhook"


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


@pytest.fixture()
def finance(db):
    return make_user(db, role=UserRole.FINANCE)


@pytest.fixture()
def finance_headers(finance):
    return headers_for(finance)


@pytest.fixture()
def order(db, customer, tour):
    return make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)


def refund(client, headers, order_id, **data):
    data = {"fpv_amount": "0", **data}
    return client.post(f"/api/finance/orders/{order_id}/refund", data=data, headers=headers)


def send(client, refund_id, status, metadata=None, event_type=None):
    """A signed refund event, as Stripe sends it; the mock is swapped for the signature checker."""
    body = {"id": f"evt_{refund_id}_{status}", "object": "event",
            "type": event_type or ("refund.failed" if status == "failed" else "refund.updated"),
            "data": {"object": {"id": refund_id, "object": "refund", "status": status, "amount": 100,
                                "payment_intent": "pi_x", "metadata": metadata or {"payment_id": "1"}}}}
    payload = json.dumps(body).encode()
    set_gateway(StripeGateway("sk_test_dummy_not_used", SECRET, settings.stripe_api_version))
    try:
        return client.post(WEBHOOK, content=payload, headers={
            "Stripe-Signature": stripe_signature(payload, SECRET), "Content-Type": "application/json"})
    finally:
        set_gateway(None)


def refund_rows(db, order_id):
    return db.scalars(select(Payment).where(Payment.order_id == order_id, Payment.type == PaymentType.REFUND)
                      .order_by(Payment.id)).all()


def test_pending_refund_is_finished_by_the_webhook(client, db, customer, finance_headers, tour, order,
                                                   gateway):
    gateway.refund_outcomes = ["pending"]                 # e.g. test card 4000000000007726
    body = refund(client, finance_headers, order.id).json()
    assert (body["finished"], body["order_status"], body["payment_status"]) == (
        False, "cancel_requested", "paid")
    assert body["rows"][0]["status"] == "pending" and "обробляє" in body["message"]
    queue = client.get("/api/finance/refunds", headers=finance_headers).json()["items"]
    assert [(i["order_id"], i["kind"], i["pending_refund_uah"]) for i in queue] == [
        (order.id, "refund_pending", "77000.00")]
    again = refund(client, finance_headers, order.id)
    assert again.status_code == 409 and "обробляється" in again.json()["detail"]
    assert db.get(Tour, tour.id).seats_sold == 2           # not cancelled yet

    gateway_set = gateway                                 # keep the mock for later assertions
    response = send(client, "mock_re_1", "succeeded")
    assert response.status_code == 200 and response.json()["result"] == "refund_succeeded"
    set_gateway(gateway_set)
    db.expire_all()
    done = db.get(Order, order.id)
    assert (done.status, done.payment_status) == (OrderStatus.CANCELLED, PaymentStatus.REFUNDED)
    assert done.history[-1].changed_by is None            # the System finished it
    assert db.get(Tour, tour.id).seats_sold == 0
    assert refund_rows(db, order.id)[0].status == TransactionStatus.SUCCEEDED
    assert send(client, "mock_re_1", "succeeded").json()["result"] == "duplicate"
    assert send(client, "mock_re_1", "pending").json()["result"] == "ignored"   # never backwards
    assert len(gateway.refunds) == 1
    note = db.scalars(select(Notification).where(Notification.user_id == customer.id)).one()
    assert note.title.endswith("повернено")


def test_failed_refund_goes_back_to_the_queue(client, db, finance, finance_headers, tour, order, gateway):
    """Test card 4000000000005126: the refund first succeeds, then fails."""
    refund(client, finance_headers, order.id)
    [card] = [p for p in order.payments if p.type == PaymentType.PAYMENT]
    response = send(client, "mock_re_1", "failed")
    assert response.json()["result"] == "refund_failed"
    set_gateway(gateway)
    db.expire_all()
    failed = db.get(Order, order.id)
    assert (failed.status, failed.payment_status) == (OrderStatus.CANCELLED, PaymentStatus.PAID)
    assert refund_rows(db, order.id)[0].status == TransactionStatus.FAILED
    assert db.get(Tour, tour.id).seats_sold == 0                       # stays cancelled
    item = client.get("/api/finance/refunds", headers=finance_headers).json()["items"][0]
    assert (item["order_id"], item["kind"], item["kept_uah"]) == (order.id, "refund_failed", "77000.00")
    note = db.scalars(select(Notification).where(Notification.user_id == finance.id)).one()
    assert "не вдалося" in note.title
    assert send(client, "mock_re_1", "succeeded").json()["result"] == "ignored"   # failed is final

    # Another way to pay the customer: a bank transfer instead of Stripe, same ФПВ (0).
    set_gateway(gateway)
    assert refund(client, finance_headers, order.id, fpv_amount="10", comment="x").status_code == 422
    manual = refund(client, finance_headers, order.id, manual="true",
                    transfer_sent_at=NOW.isoformat(), transfer_details="IBAN UA11 2233")
    assert manual.status_code == 200, manual.text
    row = manual.json()["rows"][0]
    assert (row["method"], row["refund_of_id"], row["status"]) == ("bank_transfer", card.id, "succeeded")
    assert manual.json()["payment_status"] == "refunded" and len(gateway.refunds) == 1


def test_retry_through_stripe_after_a_failure_uses_a_new_key(client, db, finance_headers, order, gateway):
    refund(client, finance_headers, order.id)
    send(client, "mock_re_1", "failed")
    set_gateway(gateway)
    assert refund(client, finance_headers, order.id).status_code == 200
    card_id = refund_rows(db, order.id)[0].refund_of_id
    assert [r["idempotency_key"] for r in gateway.refunds] == [f"refund-{card_id}-1", f"refund-{card_id}-2"]


def test_unknown_refunds(client, db):
    # Ours (metadata) but not recorded yet: the event came before our COMMIT -> Stripe retries.
    assert send(client, "re_not_yet", "succeeded").status_code == 503
    # Not ours (e.g. made by hand in the Dashboard): acknowledged and ignored.
    response = send(client, "re_dashboard", "succeeded", metadata={"note": "manual"})
    assert response.status_code == 200 and response.json()["result"] == "unknown_refund"
    # Refund events we do not use (refund.created, charge.refunded) are ignored.
    assert send(client, "re_x", "succeeded", event_type="refund.created").json()["result"] == "ignored"


def test_late_payment_refund_is_linked_to_its_payment(db, customer, tour, gateway):
    order = make_order(db, customer, tour, status=OrderStatus.CANCELLED)
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                      status=TransactionStatus.PENDING, amount_uah=order.total_uah,
                      stripe_session_id="cs_late_1")
    db.add(payment)
    db.flush()
    session = GatewaySession(id="cs_late_1", url=None, status="complete", payment_status="paid",
                             payment_intent="pi_late_1", amount_total=7700000,
                             metadata={"payment_id": str(payment.id)})
    event = GatewayEvent(id="evt_late", type="checkout.session.completed", session=session)
    assert payment_service.handle_event(db, event, gateway) == "refunded"
    [row] = refund_rows(db, order.id)
    assert row.refund_of_id == payment.id
    assert gateway.refunds[0]["idempotency_key"] == f"late-refund-{payment.id}"
    # The webhook later says this refund failed: the money is with us again, finance takes over.
    failed = GatewayEvent(id="evt_f", type="refund.failed", session=None,
                          refund=gateway.refund_event(row.stripe_refund_id, "failed").refund)
    assert payment_service.handle_event(db, failed, gateway) == "refund_failed"
    assert db.get(Order, order.id).payment_status == PaymentStatus.PAID
