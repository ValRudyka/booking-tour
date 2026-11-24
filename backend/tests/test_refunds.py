"""Finance refunds (ТЗ 4.5.6, form 4.6.3.1): queue, ФПВ, Stripe and manual refunds, mixed
payments, idempotent retries. The mock gateway records every refund call."""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Notification, Order, Payment, Tour
from app.models.enums import (OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus, UserRole)
from app.services.payments.gateway import GatewayError
from tests.factories import (add_payment, headers_for, make_active_tour, make_order,
                             make_paid_order, make_user)

NOW = datetime.now(timezone.utc)
PDF = b"%PDF-1.4\n% refund receipt\n" + b"0" * 100


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


@pytest.fixture()
def finance(db):
    return make_user(db, role=UserRole.FINANCE)


@pytest.fixture()
def finance_headers(finance):
    return headers_for(finance)


def refund(client, headers, order_id, fpv="0", comment=None, sent_at=None, details=None,
           statement=None, manual=False):
    data = {"fpv_amount": fpv, "manual": str(manual).lower()}
    if comment:
        data["comment"] = comment
    if sent_at:
        data["transfer_sent_at"] = sent_at.isoformat()
    if details:
        data["transfer_details"] = details
    files = {"statement": statement} if statement else None
    return client.post(f"/api/finance/orders/{order_id}/refund", data=data, files=files, headers=headers)


def refunds_of(db, order_id):
    return db.scalars(select(Payment).where(Payment.order_id == order_id, Payment.type == PaymentType.REFUND)
                      .order_by(Payment.id)).all()


def queue(client, headers):
    return {item["order_id"]: item for item in
            client.get("/api/finance/refunds", headers=headers).json()["items"]}


# ---------- cancellation request (4.5.5 -> 4.5.6)
def test_refund_with_fpv(client, db, customer, finance, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)
    [payment] = order.payments
    response = refund(client, finance_headers, order.id, fpv="7000", comment="Штраф туроператора 10%")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["order_status"], body["payment_status"], body["fpv_uah"], body["refunded_now_uah"],
            body["finished"]) == ("cancelled", "partially_refunded", "7000.00", "70000.00", True)
    assert gateway.refunds == [{
        "id": "mock_re_1", "payment_intent": payment.stripe_payment_intent, "amount_minor": 7000000,
        "idempotency_key": f"refund-{payment.id}-1", "status": "succeeded",
        "metadata": {"order_id": str(order.id), "payment_id": str(payment.id), "reason": "finance_refund"}}]
    db.expire_all()
    [row] = refunds_of(db, order.id)
    assert (row.status, row.amount_uah, row.refund_of_id, row.stripe_refund_id, row.confirmed_by,
            row.controller_comment) == (TransactionStatus.SUCCEEDED, Decimal("70000.00"), payment.id,
                                        "mock_re_1", finance.id, "Штраф туроператора 10%")
    assert db.get(Tour, tour.id).seats_sold == 0                       # seats back with the cancel
    cancelled = db.get(Order, order.id)
    assert cancelled.history[-1].changed_by == finance.id
    note = db.scalars(select(Notification).where(Notification.user_id == customer.id)).one()
    assert "Повернено 70000.00 грн" in note.body and "7000.00 грн" in note.body


def test_refund_without_fpv(client, db, customer, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)
    body = refund(client, finance_headers, order.id).json()
    assert (body["order_status"], body["payment_status"], body["refunded_now_uah"]) == (
        "cancelled", "refunded", "77000.00")


def test_fpv_validation(client, db, customer, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)
    no_comment = refund(client, finance_headers, order.id, fpv="100")
    assert no_comment.status_code == 422 and "коментар" in no_comment.json()["detail"]
    assert refund(client, finance_headers, order.id, fpv="-1", comment="x").status_code == 422
    too_much = refund(client, finance_headers, order.id, fpv="77000.01", comment="x")
    assert too_much.status_code == 422 and "77000.00" in too_much.json()["detail"]
    assert gateway.refund_calls == 0
    # ФПВ = everything paid: nothing goes back, the order is still cancelled.
    body = refund(client, finance_headers, order.id, fpv="77000", comment="Тур не повертається").json()
    assert (body["order_status"], body["payment_status"], body["rows"]) == ("cancelled", "paid", [])


def test_duplicate_request_does_not_refund_twice(client, db, customer, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)
    assert refund(client, finance_headers, order.id).status_code == 200
    again = refund(client, finance_headers, order.id)
    assert again.status_code == 409 and "уже повернено" in again.json()["detail"]
    assert len(gateway.refunds) == 1 and gateway.refund_calls == 1
    assert len(refunds_of(db, order.id)) == 1


# ---------- rejected by the manager (4.5.4 step 4.1): full refund
def test_rejected_order_full_refund_then_archive(client, db, customer, manager, manager_headers,
                                                 finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.REJECTED, manager_id=manager.id)
    with_fpv = refund(client, finance_headers, order.id, fpv="10", comment="x")
    assert with_fpv.status_code == 422 and "ФПВ = 0" in with_fpv.json()["detail"]
    body = refund(client, finance_headers, order.id).json()
    assert (body["order_status"], body["payment_status"]) == ("rejected", "refunded")
    assert order.id not in queue(client, finance_headers)
    archived = client.post(f"/api/manager/orders/{order.id}/archive", headers=manager_headers)
    assert archived.status_code == 200 and archived.json()["status"] == "archived"


# ---------- mixed payments: newest first, bank parts by transfer
def test_mixed_payments_newest_first(client, db, customer, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED, payments=[])
    bank = add_payment(db, order, "30000.00", PaymentMethod.BANK_TRANSFER, received_at=NOW - timedelta(days=3))
    card = add_payment(db, order, "47000.00", PaymentMethod.CARD, received_at=NOW - timedelta(days=1))

    # 67 000 back: 47 000 from the card (newest), 20 000 from the transfer; ФПВ stays on the oldest.
    missing = refund(client, finance_headers, order.id, fpv="10000", comment="ФПВ готелю")
    assert missing.status_code == 422 and "реквізити переказу" in missing.json()["detail"]
    assert gateway.refund_calls == 0                       # checked before anything is sent
    response = refund(client, finance_headers, order.id, fpv="10000", comment="ФПВ готелю",
                      sent_at=NOW - timedelta(hours=1), details="IBAN UA12 3456, Шевченко Т.",
                      statement=("receipt.pdf", PDF, "application/pdf"))
    assert response.status_code == 200, response.text
    assert [(r["refund_of_id"], r["method"], r["amount_uah"]) for r in response.json()["rows"]] == [
        (card.id, "card", "47000.00"), (bank.id, "bank_transfer", "20000.00")]
    assert [r["amount_minor"] for r in gateway.refunds] == [4700000]
    db.expire_all()
    bank_row = refunds_of(db, order.id)[1]
    assert bank_row.purpose == "IBAN UA12 3456, Шевченко Т." and bank_row.stripe_refund_id is None
    assert bank_row.bank_statement_path.startswith(f"private/statements/refunds/{order.id}/")
    assert (Path(settings.upload_dir) / bank_row.bank_statement_path).read_bytes() == PDF
    assert db.get(Order, order.id).payment_status == PaymentStatus.PARTIALLY_REFUNDED


def test_partial_stripe_failure_is_retried_safely(client, db, customer, finance_headers, tour, gateway,
                                                  caplog):
    """Card part 1 is refunded in Stripe, part 2 fails: the DB is rolled back, finance repeats the
    same request, Stripe replays part 1 by its idempotency key -> one refund per part."""
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED, payments=[])
    older = add_payment(db, order, "37000.00", PaymentMethod.CARD, received_at=NOW - timedelta(days=2))
    newer = add_payment(db, order, "40000.00", PaymentMethod.CARD, received_at=NOW - timedelta(days=1))
    gateway.refund_outcomes = ["succeeded", GatewayError("Stripe is down")]

    with caplog.at_level(logging.WARNING, logger="tour.payments"):
        failed = refund(client, finance_headers, order.id)
    assert failed.status_code == 502
    assert "повторіть той самий запит" in failed.json()["detail"]
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    text = warning.getMessage()
    assert str(order.id) in text and str(newer.id) in text and str(older.id) in text and "mock_re_1" in text
    db.expire_all()
    assert refunds_of(db, order.id) == []                  # nothing recorded
    assert db.get(Order, order.id).status == OrderStatus.CANCEL_REQUESTED

    retry = refund(client, finance_headers, order.id)
    assert retry.status_code == 200, retry.text
    assert [(r["refund_of_id"], r["stripe_refund_id"]) for r in retry.json()["rows"]] == [
        (newer.id, "mock_re_1"), (older.id, "mock_re_2")]
    assert len(gateway.refunds) == 2                       # exactly one Stripe refund per part
    assert [r["idempotency_key"] for r in gateway.refunds] == [f"refund-{newer.id}-1", f"refund-{older.id}-1"]
    db.expire_all()
    assert len(refunds_of(db, order.id)) == 2
    assert db.get(Order, order.id).status == OrderStatus.CANCELLED


def test_retry_with_another_amount_is_refused(client, db, customer, finance_headers, tour, gateway):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED, payments=[])
    add_payment(db, order, "37000.00", PaymentMethod.CARD, received_at=NOW - timedelta(days=2))
    add_payment(db, order, "40000.00", PaymentMethod.CARD, received_at=NOW - timedelta(days=1))
    gateway.refund_outcomes = ["succeeded", GatewayError("Stripe is down")]
    assert refund(client, finance_headers, order.id).status_code == 502      # 40 000 left in Stripe
    # Now only 32 000 would go back, so the newest part (already 40 000 in Stripe) changes:
    # Stripe refuses the reused key with other parameters, nothing is recorded.
    other = refund(client, finance_headers, order.id, fpv="45000", comment="Передумали")
    assert other.status_code == 409 and "тією самою сумою ФПВ" in other.json()["detail"]
    assert len(gateway.refunds) == 1 and refunds_of(db, order.id) == []
    # A smaller ФПВ that keeps the first part the same is consistent with Stripe and goes through.
    same_first = refund(client, finance_headers, order.id, fpv="5000", comment="Штраф")
    assert same_first.status_code == 200 and len(gateway.refunds) == 2


# ---------- partly paid transfer order the client never finished (decided with the owner)
def test_unfinished_transfer_is_cancelled_and_refunded(client, db, customer, finance_headers, tour):
    order = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT,
                       payment_status=PaymentStatus.PARTIALLY_PAID, hold_expires_at=NOW - timedelta(hours=1))
    add_payment(db, order, "20000.00", PaymentMethod.BANK_TRANSFER)
    assert queue(client, finance_headers)[order.id]["kind"] == "unfinished_transfer"
    assert refund(client, finance_headers, order.id, fpv="100", comment="x").status_code == 422
    body = refund(client, finance_headers, order.id, sent_at=NOW, details="IBAN UA99").json()
    assert (body["order_status"], body["payment_status"], body["refunded_now_uah"]) == (
        "cancelled", "refunded", "20000.00")


def test_refund_not_possible_in_other_statuses(client, db, customer, finance_headers, tour):
    for status in (OrderStatus.PAID, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED):
        order = make_paid_order(db, customer, tour, status=status)
        response = refund(client, finance_headers, order.id)
        assert response.status_code == 409 and "не оформлюється" in response.json()["detail"]
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT)
    assert refund(client, finance_headers, waiting.id).status_code == 409
    assert refund(client, finance_headers, 999999).status_code == 404


# ---------- the queue
def test_queue_shows_only_orders_that_owe_money(client, db, customer, finance_headers, tour):
    requested = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED,
                                cancel_reason="Хвороба")
    rejected = make_paid_order(db, customer, tour, status=OrderStatus.REJECTED, reject_reason="Немає місць")
    make_paid_order(db, customer, tour, status=OrderStatus.PAID)
    make_order(db, customer, tour, status=OrderStatus.CANCELLED)                 # timeout, never paid
    done = make_paid_order(db, customer, tour, status=OrderStatus.REJECTED)
    refund(client, finance_headers, done.id)
    items = queue(client, finance_headers)
    assert set(items) == {requested.id, rejected.id}
    item = items[requested.id]
    assert (item["kind"], item["paid_uah"], item["kept_uah"], item["refunded_uah"], item["cancel_reason"]) == (
        "cancel_request", "77000.00", "77000.00", "0.00", "Хвороба")
    assert items[rejected.id]["kind"] == "rejected"


def test_finance_sees_the_order_without_the_internal_comment(client, db, customer, finance_headers, tour):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED,
                            internal_comment="Лише для менеджерів")
    body = client.get(f"/api/finance/orders/{order.id}", headers=finance_headers).json()
    assert body["internal_comment"] is None and body["payments"][0]["status"] == "succeeded"
    assert client.get("/api/finance/orders/999999", headers=finance_headers).status_code == 404


# ---------- access
@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.ADMIN])
def test_refunds_only_for_finance(client, db, customer, tour, role):
    order = make_paid_order(db, customer, tour, status=OrderStatus.CANCEL_REQUESTED)
    headers = headers_for(make_user(db, role=role))
    assert refund(client, headers, order.id).status_code == 403
    assert client.get("/api/finance/refunds", headers=headers).status_code == 403
    assert client.get(f"/api/finance/orders/{order.id}", headers=headers).status_code == 403
    assert refund(client, {}, order.id).status_code == 401
    assert db.get(Order, order.id).status == OrderStatus.CANCEL_REQUESTED
