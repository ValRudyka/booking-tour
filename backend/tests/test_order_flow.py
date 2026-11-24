"""End-to-end order life cycles through the API (ТЗ 4.4, 4.4.1): payment (mock Stripe page),
manager processing, documents, completion by the System, cancellation and refunds, archive."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Notification, Order, Tour
from app.models.enums import OrderStatus, UserRole
from app.services.order_completion import complete_orders
from app.services import clock
from tests.factories import headers_for, make_active_tour, make_order, make_user

NOW = datetime.now(timezone.utc)
PDF = b"%PDF-1.4\n% voucher\n" + b"0" * 100
M = "/api/manager/orders"


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)                       # 10 seats, starts in 30 days


@pytest.fixture()
def finance_headers(db):
    return headers_for(make_user(db, role=UserRole.FINANCE))


@pytest.fixture()
def paid_order(client, db, customer, customer_headers, tour, gateway):
    """Checkout done; the client pays by card on the (mock) Stripe page; the webhook marks it paid."""
    start = tour.departure_from
    order = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT, adults=2,
                       total_uah=Decimal("77500.00"), start_date=start, end_date=start + timedelta(days=7),
                       hold_expires_at=NOW + timedelta(minutes=20))
    pay = client.post(f"/api/orders/{order.id}/pay", json={"method": "card"}, headers=customer_headers)
    assert pay.status_code == 200, pay.text
    assert client.post(f"/api/payments/mock/{gateway.created[0]}/succeed").json()["result"] == "paid"
    db.expire_all()
    assert db.get(Tour, tour.id).seats_sold == 2
    return db.get(Order, order.id)


def history(client, headers, order_id):
    return [(h["new_status"], h["changed_by"])
            for h in client.get(f"{M}/{order_id}", headers=headers).json()["history"]]


def client_notes(db, customer):
    return [n.title for n in db.scalars(select(Notification).where(Notification.user_id == customer.id)
                                        .order_by(Notification.id))]


def test_happy_path(client, db, customer, customer_headers, manager, manager_headers, paid_order):
    order = paid_order
    n = order.number
    assert client_notes(db, customer) == [f"Замовлення {n} оплачено"]

    assert client.post(f"{M}/{order.id}/take", headers=manager_headers).status_code == 200
    deadline = (clock.today() + timedelta(days=7)).isoformat()
    assert client.post(f"{M}/{order.id}/confirm", json={"pnr": "XK7Q2P", "operator_deadline": deadline},
                       headers=manager_headers).status_code == 200
    assert client_notes(db, customer)[-1] == f"Бронювання {n} підтверджено"

    upload = client.post(f"{M}/{order.id}/documents", data={"doc_type": "voucher"},
                         files=[("files", ("voucher.pdf", PDF, "application/pdf"))], headers=manager_headers)
    assert upload.status_code == 201
    assert client.post(f"{M}/{order.id}/documents-ready", headers=manager_headers).status_code == 200
    assert client_notes(db, customer)[-1] == f"Документи до замовлення {n} готові"
    [doc] = client.get(f"/api/orders/{order.id}/documents", headers=customer_headers).json()
    assert client.get(f"/api/orders/{order.id}/documents/{doc['id']}/download",
                      headers=customer_headers).content == PDF

    assert complete_orders(db, order.end_date) == 0               # still travelling
    assert complete_orders(db, order.end_date + timedelta(days=1)) == 1
    assert client_notes(db, customer)[-1] == f"Подорож за замовленням {n} завершено"

    assert client.post(f"{M}/{order.id}/archive", headers=manager_headers).json()["status"] == "archived"
    assert history(client, manager_headers, order.id) == [
        ("paid", None), ("in_progress", manager.id), ("confirmed", manager.id),
        ("documents_ready", manager.id), ("completed", None), ("archived", manager.id)]
    # Archived orders leave the working list but keep everything (4.5.9 step 4).
    assert client.get(M, headers=manager_headers).json()["total"] == 0
    assert len(client.get(f"/api/orders/{order.id}/documents", headers=customer_headers).json()) == 1
    assert client_notes(db, customer)[-1] == f"Подорож за замовленням {n} завершено"   # no note for archive


def test_reject_path(client, db, customer, manager, manager_headers, finance_headers, tour, paid_order,
                     gateway):
    order = paid_order
    client.post(f"{M}/{order.id}/take", headers=manager_headers)
    response = client.post(f"{M}/{order.id}/reject", json={"reject_reason": "Готель закрито на ремонт"},
                           headers=manager_headers)
    assert response.json()["status"] == "rejected"
    db.expire_all()
    assert db.get(Tour, tour.id).seats_sold == 0                   # seats back at once
    assert client.post(f"{M}/{order.id}/archive", headers=manager_headers).status_code == 409

    queue = client.get("/api/finance/refunds", headers=finance_headers).json()["items"]
    assert [(i["order_id"], i["kind"], i["kept_uah"]) for i in queue] == [(order.id, "rejected", "77500.00")]
    refund = client.post(f"/api/finance/orders/{order.id}/refund", data={"fpv_amount": "0"},
                         headers=finance_headers).json()
    assert (refund["order_status"], refund["payment_status"]) == ("rejected", "refunded")
    assert [r["amount_minor"] for r in gateway.refunds] == [7750000]
    assert client.get("/api/finance/refunds", headers=finance_headers).json()["total"] == 0

    assert client.post(f"{M}/{order.id}/archive", headers=manager_headers).status_code == 200
    assert history(client, manager_headers, order.id) == [
        ("paid", None), ("in_progress", manager.id), ("rejected", manager.id), ("archived", manager.id)]
    assert client_notes(db, customer)[1:] == [f"Замовлення {order.number} відхилено",
                                             f"Кошти за замовленням {order.number} повернено"]


def test_cancellation_path(client, db, customer, customer_headers, manager, manager_headers,
                           finance_headers, tour, paid_order, gateway):
    order = paid_order
    client.post(f"{M}/{order.id}/take", headers=manager_headers)
    client.post(f"{M}/{order.id}/confirm", headers=manager_headers,
                json={"pnr": "XK7Q2P", "operator_deadline": (clock.today() + timedelta(days=7)).isoformat()})
    request = client.post(f"/api/orders/{order.id}/cancel-request", headers=customer_headers,
                          data={"reason_code": "change_of_plans", "accept_penalty_policy": "true"})
    assert request.json()["status"] == "cancel_requested"
    db.expire_all()
    assert db.get(Tour, tour.id).seats_sold == 2                   # until the money is back

    refund = client.post(f"/api/finance/orders/{order.id}/refund", headers=finance_headers,
                         data={"fpv_amount": "15500", "comment": "Авіаквитки не повертаються"}).json()
    assert (refund["order_status"], refund["payment_status"], refund["refunded_now_uah"]) == (
        "cancelled", "partially_refunded", "62000.00")
    db.expire_all()
    assert db.get(Tour, tour.id).seats_sold == 0
    mine = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert (mine["status"], mine["fpv_uah"], mine["cancel_reason_code"]) == (
        "cancelled", "15500.00", "change_of_plans")
    assert client.post(f"{M}/{order.id}/archive", headers=manager_headers).status_code == 200
    assert [s for s, _ in history(client, manager_headers, order.id)] == [
        "paid", "in_progress", "confirmed", "cancel_requested", "cancelled", "archived"]
