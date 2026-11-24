"""Bank transfer (ТЗ 4.4 step 5) and the finance register / confirmation (form 4.6.3.1)."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, Order, Payment, Setting, Tour
from app.models.enums import OrderStatus, PaymentMethod, TransactionStatus, UserRole
from app.services.order_expiry import expire_orders
from tests.factories import headers_for, make_active_tour, make_order, make_user

NOW = datetime.now(timezone.utc)
REGISTER = "/api/finance/payments"
PDF = b"%PDF-1.4\n% bank statement\n" + b"0" * 200


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


@pytest.fixture()
def order(db, customer, tour):
    return make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT, adults=2,
                      total_uah=Decimal("77500.00"), hold_expires_at=NOW + timedelta(minutes=20))


@pytest.fixture()
def finance(db):
    return make_user(db, role=UserRole.FINANCE)


@pytest.fixture()
def finance_headers(finance):
    return headers_for(finance)


def pay_by_transfer(client, headers, order_id):
    response = client.post(f"/api/orders/{order_id}/pay", json={"method": "bank_transfer"},
                           headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, headers, payment_id, amount, purpose="Оплата туру TU-1", received=None,
            statement=None, comment=None):
    data = {"paid_amount": str(amount), "purpose": purpose,
            "received_at": (received or NOW - timedelta(hours=1)).isoformat()}
    if comment:
        data["comment"] = comment
    files = {"statement": statement} if statement else None
    return client.post(f"{REGISTER}/{payment_id}/confirm", data=data, files=files, headers=headers)


def hold_audit(db, order_id):
    return db.scalars(select(AuditLog).where(AuditLog.entity == "order", AuditLog.action == "hold_extended",
                                             AuditLog.entity_id == str(order_id))
                      .order_by(AuditLog.id)).all()


# ---------- the client chooses a transfer
def test_transfer_gives_details_and_extends_the_hold_once(client, db, customer, customer_headers, order):
    body = pay_by_transfer(client, customer_headers, order.id)
    details = body["bank_details"]
    assert (details["iban"], details["amount_uah"]) == (settings.bank_iban, "77500.00")
    assert order.number in details["purpose"] and customer.last_name in details["purpose"]
    assert body["payment"]["method"] == "bank_transfer" and body["payment"]["status"] == "pending"
    hold = datetime.fromisoformat(details["pay_until"])
    assert timedelta(hours=47) < hold - NOW < timedelta(hours=49)          # default 48 h
    assert [a.new_value["reason"] for a in hold_audit(db, order.id)] == ["bank_transfer_chosen"]

    again = pay_by_transfer(client, customer_headers, order.id)
    assert again["payment"]["id"] == body["payment"]["id"]
    assert again["bank_details"]["pay_until"] == details["pay_until"]       # not extended again
    assert len(hold_audit(db, order.id)) == 1


def test_hold_hours_come_from_settings(client, db, customer_headers, order):
    db.get(Setting, "bank_transfer_hold_hours").value = 72
    db.flush()
    hold = datetime.fromisoformat(pay_by_transfer(client, customer_headers, order.id)
                                  ["bank_details"]["pay_until"])
    assert timedelta(hours=71) < hold - NOW < timedelta(hours=73)


def test_switching_from_card_closes_the_session(client, db, customer_headers, order, gateway):
    client.post(f"/api/orders/{order.id}/pay", json={"method": "card"}, headers=customer_headers)
    pay_by_transfer(client, customer_headers, order.id)
    assert gateway.expire_calls == gateway.created
    card = db.scalar(select(Payment).where(Payment.order_id == order.id,
                                           Payment.method == PaymentMethod.CARD))
    assert card.status == TransactionStatus.FAILED


# ---------- the finance controller confirms
def test_partial_then_full_payment(client, db, customer_headers, finance, finance_headers, order):
    first_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    response = confirm(client, finance_headers, first_id, "30000", comment="Перша частина")
    assert response.status_code == 200, response.text
    first = response.json()
    assert (first["status"], first["paid_amount"], first["order_payment_status"]) == (
        "succeeded", "30000.00", "partially_paid")
    assert first["order_status"] == "awaiting_payment"
    assert [a.new_value["reason"] for a in hold_audit(db, order.id)] == [
        "bank_transfer_chosen", "partial_payment"]

    rest = db.scalar(select(Payment).where(Payment.order_id == order.id,
                                           Payment.status == TransactionStatus.PENDING))
    assert (rest.amount_uah, rest.method) == (Decimal("47500.00"), PaymentMethod.BANK_TRANSFER)
    assert order.number in rest.purpose                       # the expected purpose, not the bank's text

    second = confirm(client, finance_headers, rest.id, "47500").json()
    assert (second["order_status"], second["order_payment_status"]) == ("paid", "paid")
    db.expire_all()
    paid = db.get(Order, order.id)
    assert db.get(Tour, paid.tour_id).seats_sold == 2
    assert (paid.history[-1].new_status, paid.history[-1].changed_by) == ("paid", finance.id)
    assert db.get(Payment, first_id).confirmed_by == finance.id


def test_partly_paid_order_is_not_cancelled_automatically(client, db, customer_headers,
                                                          finance_headers, order):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    confirm(client, finance_headers, payment_id, "1000")
    db.get(Order, order.id).hold_expires_at = NOW - timedelta(minutes=1)
    db.flush()
    assert expire_orders(db) == 0
    response = client.post(f"/api/orders/{order.id}/cancel", headers=customer_headers)
    assert response.status_code == 409
    assert db.get(Order, order.id).status == OrderStatus.AWAITING_PAYMENT


@pytest.mark.parametrize("amount,overrides,message", [
    ("77500.01", {}, "більша за очікувану"),
    ("0", {}, "більшою за 0"),
    ("100", {"purpose": "   "}, "призначення платежу"),
    ("100", {"received": NOW + timedelta(days=1)}, "в майбутньому"),
])
def test_confirm_validation(client, db, customer_headers, finance_headers, order, amount,
                            overrides, message):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    response = confirm(client, finance_headers, payment_id, amount, **overrides)
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert db.get(Payment, payment_id).status == TransactionStatus.PENDING


def test_only_pending_transfers_of_waiting_orders(client, db, customer_headers, finance_headers,
                                                  order, gateway):
    client.post(f"/api/orders/{order.id}/pay", json={"method": "card"}, headers=customer_headers)
    card_id = db.scalar(select(Payment.id).where(Payment.order_id == order.id))
    assert confirm(client, finance_headers, card_id, "77500").status_code == 409

    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    assert confirm(client, finance_headers, payment_id, "77500").status_code == 200
    assert confirm(client, finance_headers, payment_id, "77500").status_code == 409   # already done
    assert confirm(client, finance_headers, 999999, "1").status_code == 404


def test_cancelled_order_cannot_be_credited(client, db, customer_headers, finance_headers, order):
    from app.services.order_status import change_status

    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    change_status(db, order, OrderStatus.CANCELLED, None)
    response = confirm(client, finance_headers, payment_id, "77500")
    assert response.status_code == 409
    assert "«Скасовано»" in response.json()["detail"]


# ---------- bank statement: private file
def test_statement_is_private(client, db, customer_headers, finance_headers, order):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    body = confirm(client, finance_headers, payment_id, "77500",
                   statement=("../../statement.pdf", PDF, "application/pdf")).json()
    assert body["has_statement"] is True
    stored = db.get(Payment, payment_id).bank_statement_path
    assert stored.startswith(f"private/statements/{payment_id}/") and stored.endswith(".pdf")
    assert (Path(settings.upload_dir) / stored).read_bytes() == PDF

    download = client.get(f"{REGISTER}/{payment_id}/statement", headers=finance_headers)
    assert download.status_code == 200 and download.content == PDF
    assert "attachment" in download.headers["content-disposition"]
    assert client.get(f"{REGISTER}/{payment_id}/statement", headers=customer_headers).status_code == 403
    assert client.get(f"{REGISTER}/{payment_id}/statement").status_code == 401
    for url in (f"/uploads/{stored}", f"/uploads/tours/../{stored}",
                f"/uploads/tours/%2e%2e/{stored}"):
        response = client.get(url)
        assert response.status_code == 404, url
        assert response.content != PDF


def test_statement_must_be_pdf_or_image(client, db, customer_headers, finance_headers, order):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    response = confirm(client, finance_headers, payment_id, "77500",
                       statement=("statement.pdf", b"not a pdf at all", "application/pdf"))
    assert response.status_code == 422
    assert db.get(Payment, payment_id).status == TransactionStatus.PENDING
    assert not (Path(settings.upload_dir) / "private" / "statements" / str(payment_id)).exists() or \
        not any((Path(settings.upload_dir) / "private" / "statements" / str(payment_id)).iterdir())


def test_no_statement_is_404(client, customer_headers, finance_headers, order):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    confirm(client, finance_headers, payment_id, "77500")
    assert client.get(f"{REGISTER}/{payment_id}/statement", headers=finance_headers).status_code == 404


# ---------- register and access
def test_register_filters(client, db, customer, customer_headers, finance_headers, tour, order, gateway):
    other = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT, adults=1,
                       total_uah=Decimal("40000.00"), hold_expires_at=NOW + timedelta(minutes=20))
    transfer_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    client.post(f"/api/orders/{other.id}/pay", json={"method": "card"}, headers=customer_headers)
    confirm(client, finance_headers, transfer_id, "77500")

    def ids(**params):
        response = client.get(REGISTER, params=params, headers=finance_headers)
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    card_id = db.scalar(select(Payment.id).where(Payment.order_id == other.id))
    assert ids() == [card_id, transfer_id]                         # newest first
    assert ids(status="succeeded") == [transfer_id]
    assert ids(method="card") == [card_id]
    assert ids(type="payment", order_number=order.number) == [transfer_id]
    assert ids(type="refund") == []
    assert ids(date_from=date.today().isoformat(), date_to=date.today().isoformat()) == [card_id, transfer_id]
    assert ids(date_to=(date.today() - timedelta(days=1)).isoformat()) == []
    page = client.get(REGISTER, params={"page_size": 1, "page": 2}, headers=finance_headers).json()
    assert (page["total"], [r["id"] for r in page["items"]]) == (2, [transfer_id])
    row = client.get(REGISTER, params={"status": "succeeded"}, headers=finance_headers).json()["items"][0]
    assert (row["order_number"], row["amount_uah"], row["paid_amount"], row["currency"]) == (
        order.number, "77500.00", "77500.00", "UAH")


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.ADMIN])
def test_finance_endpoints_only_for_finance(client, db, customer_headers, order, role):
    payment_id = pay_by_transfer(client, customer_headers, order.id)["payment"]["id"]
    headers = headers_for(make_user(db, role=role))
    assert client.get(REGISTER, headers=headers).status_code == 403
    assert confirm(client, headers, payment_id, "77500").status_code == 403
    assert client.get(REGISTER).status_code == 401
    assert db.get(Payment, payment_id).status == TransactionStatus.PENDING
