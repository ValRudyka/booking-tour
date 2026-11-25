"""Manager's processing of orders (ТЗ 4.5.4, 4.5.9, form 4.6.2.2) and who may do what."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, Order, Tour
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus, UserRole
from app.services.order_status import change_status
from app.services import clock
from tests.factories import (add_payment, headers_for, make_active_tour, make_order,
                             make_paid_order, make_user)

URL = "/api/manager/orders"
DEADLINE = (clock.today() + timedelta(days=10)).isoformat()


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)                     # 10 seats, starts in 30 days


@pytest.fixture()
def order(db, customer, tour):
    return make_paid_order(db, customer, tour, start_date=tour.departure_from,
                           end_date=tour.departure_from + timedelta(days=7))


@pytest.fixture()
def other_manager(db):
    return make_user(db, role=UserRole.MANAGER)


def take(client, headers, order_id):
    return client.post(f"{URL}/{order_id}/take", headers=headers)


def confirm(client, headers, order_id, pnr="ABC123", deadline=DEADLINE, message=None):
    body = {"pnr": pnr, "operator_deadline": deadline}
    if message:
        body["client_message"] = message
    return client.post(f"{URL}/{order_id}/confirm", json=body, headers=headers)


def reject(client, headers, order_id, reason="Немає місць у готелі"):
    return client.post(f"{URL}/{order_id}/reject", json={"reject_reason": reason}, headers=headers)


# ---------- list and detail
def test_list_filters_and_archived_hidden(client, db, manager, manager_headers, customer, tour, order):
    other_tour = make_active_tour(db, manager, days_ahead=60)
    later = make_paid_order(db, customer, other_tour, start_date=other_tour.departure_from,
                            end_date=other_tour.departure_from + timedelta(days=7))
    archived = make_order(db, customer, tour, status=OrderStatus.ARCHIVED)
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT)

    def ids(**params):
        body = client.get(URL, params=params, headers=manager_headers).json()
        return {item["id"] for item in body["items"]}, body["total"]

    assert ids() == ({order.id, later.id, waiting.id}, 3)
    assert ids(status="paid") == ({order.id, later.id}, 2)
    assert ids(status=["paid", "archived"])[0] == {order.id, later.id, archived.id}
    assert ids(tour_id=other_tour.id)[0] == {later.id}
    assert ids(start_from=other_tour.departure_from.isoformat(), status="paid")[0] == {later.id}
    assert ids(start_to=tour.departure_from.isoformat(), status="paid")[0] == {order.id}
    assert ids(number=order.number)[0] == {order.id}
    assert ids(mine=True) == (set(), 0)
    take(client, manager_headers, order.id)
    assert ids(mine=True)[0] == {order.id}
    page = client.get(URL, params={"page_size": 1, "page": 2}, headers=manager_headers).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    row = client.get(URL, params={"number": order.number}, headers=manager_headers).json()["items"][0]
    assert row["client_name"] == "Шевченко Тарас" and row["manager_name"] == "Шевченко Т."


def test_overdue_filter(client, db, manager_headers, customer, tour, order):
    past = make_paid_order(db, customer, tour, start_date=clock.today() - timedelta(days=1),
                           end_date=clock.today() + timedelta(days=6))
    body = client.get(URL, params={"overdue": True}, headers=manager_headers).json()
    assert [i["id"] for i in body["items"]] == [past.id]


def test_detail_shows_passports_payments_history(client, manager_headers, order):
    body = client.get(f"{URL}/{order.id}", headers=manager_headers).json()
    assert len(body["tourists"]) == 2 and body["tourists"][0]["passport_number"] == "FX100000"
    assert body["client"]["phone"].startswith("+38050")
    assert body["payments"][0]["status"] == "succeeded"
    assert body["internal_comment"] is None and body["documents"] == [] and "history" in body
    assert client.get(f"{URL}/999999", headers=manager_headers).status_code == 404


# ---------- take / confirm / reject
def test_take_assigns_the_manager(client, db, manager, manager_headers, other_manager, order):
    response = take(client, manager_headers, order.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["manager_id"]) == ("in_progress", manager.id)
    assert body["history"][-1]["changed_by"] == manager.id
    again = take(client, headers_for(other_manager), order.id)
    assert again.status_code == 409 and "інший менеджер (Шевченко Т.)" in again.json()["detail"]
    assert take(client, manager_headers, order.id).status_code == 409    # already in progress


def test_only_paid_orders_can_be_taken(client, db, customer, tour, manager_headers):
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT)
    response = take(client, manager_headers, waiting.id)
    assert response.status_code == 409 and "«Оплачено»" in response.json()["detail"]


def test_confirm_needs_pnr_and_deadline(client, db, customer, manager_headers, order):
    take(client, manager_headers, order.id)
    assert confirm(client, manager_headers, order.id, pnr="a-1").status_code == 422
    assert confirm(client, manager_headers, order.id,
                   deadline=(clock.today() - timedelta(days=1)).isoformat()).status_code == 422
    assert confirm(client, manager_headers, order.id,
                   deadline=(order.start_date + timedelta(days=1)).isoformat()).status_code == 422
    assert client.post(f"{URL}/{order.id}/confirm", json={"pnr": "ABC123"},
                       headers=manager_headers).status_code == 422
    response = confirm(client, manager_headers, order.id, pnr="abc123", message="Виліт о 06:00")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["pnr"], body["operator_deadline"]) == ("confirmed", "ABC123", DEADLINE)
    note = db.scalars(select(Notification).where(Notification.user_id == customer.id)).all()[-1]
    assert "ABC123" in note.body and note.body.endswith("Виліт о 06:00")


def test_reject_returns_seats_and_tells_finance(client, db, customer, manager_headers, tour, order):
    finance = make_user(db, role=UserRole.FINANCE)
    take(client, manager_headers, order.id)
    assert reject(client, manager_headers, order.id, reason="  ").status_code == 422
    response = reject(client, manager_headers, order.id)
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["reject_reason"]) == ("rejected", "Немає місць у готелі")
    db.expire_all()
    assert db.get(Tour, tour.id).seats_sold == 0
    client_note = db.scalars(select(Notification).where(Notification.user_id == customer.id)).one()
    assert client_note.title.endswith("відхилено") and "Немає місць у готелі" in client_note.body
    finance_note = db.scalars(select(Notification).where(Notification.user_id == finance.id)).one()
    assert "повне повернення" in finance_note.body


def test_confirm_and_reject_only_in_progress(client, manager_headers, order):
    assert confirm(client, manager_headers, order.id).status_code == 409
    assert reject(client, manager_headers, order.id).status_code == 409


# ---------- the responsible manager
def test_other_manager_can_view_but_not_change(client, db, manager_headers, other_manager, order):
    take(client, manager_headers, order.id)
    other = headers_for(other_manager)
    assert client.get(f"{URL}/{order.id}", headers=other).status_code == 200
    calls = [
        lambda: confirm(client, other, order.id),
        lambda: reject(client, other, order.id),
        lambda: client.patch(f"{URL}/{order.id}", json={"internal_comment": "x"}, headers=other),
        lambda: client.post(f"{URL}/{order.id}/documents-ready", headers=other),
        lambda: client.post(f"{URL}/{order.id}/archive", headers=other),
        lambda: client.post(f"{URL}/{order.id}/assign", json={"manager_id": other_manager.id}, headers=other),
        lambda: client.post(f"{URL}/{order.id}/documents", data={"doc_type": "voucher"},
                            files=[("files", ("v.pdf", b"%PDF-1.4 x", "application/pdf"))], headers=other),
    ]
    for call in calls:
        response = call()
        assert response.status_code == 409, response.text
        assert "Змінювати його може лише відповідальний менеджер" in response.json()["detail"]
    assert db.get(Order, order.id).status == OrderStatus.IN_PROGRESS


def test_assign_hands_the_order_over(client, db, manager, manager_headers, other_manager, order):
    take(client, manager_headers, order.id)
    finance = make_user(db, role=UserRole.FINANCE)
    bad = client.post(f"{URL}/{order.id}/assign", json={"manager_id": finance.id}, headers=manager_headers)
    assert bad.status_code == 422
    response = client.post(f"{URL}/{order.id}/assign", json={"manager_id": other_manager.id},
                           headers=manager_headers)
    assert response.status_code == 200 and response.json()["manager_id"] == other_manager.id
    log = db.scalars(select(AuditLog).where(AuditLog.action == "manager_assigned")).one()
    assert (log.user_id, log.old_value, log.new_value) == (
        manager.id, {"manager_id": manager.id}, {"manager_id": other_manager.id})
    assert db.scalars(select(Notification).where(Notification.user_id == other_manager.id)).one()
    assert confirm(client, manager_headers, order.id).status_code == 409          # not mine any more
    assert confirm(client, headers_for(other_manager), order.id).status_code == 200


def test_patch_changes_only_the_internal_comment(client, manager_headers, order):
    take(client, manager_headers, order.id)
    response = client.patch(f"{URL}/{order.id}", json={"internal_comment": " Клієнт VIP "},
                            headers=manager_headers)
    assert response.status_code == 200 and response.json()["internal_comment"] == "Клієнт VIP"
    assert client.patch(f"{URL}/{order.id}", json={"internal_comment": "x", "pnr": "HACKED"},
                        headers=manager_headers).status_code == 422
    assert client.patch(f"{URL}/{order.id}", json={"internal_comment": "x" * 5001},
                        headers=manager_headers).status_code == 422
    # The client never sees the internal comment.
    assert "internal_comment" not in client.get(f"/api/orders/{order.id}",
                                                headers=headers_for(order.client)).json()


# ---------- archive (4.5.9)
def test_archive_rules(client, db, customer, manager_headers, tour, order):
    assert client.post(f"{URL}/{order.id}/archive", headers=manager_headers).status_code == 409   # paid
    completed = make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED)
    response = client.post(f"{URL}/{completed.id}/archive", headers=manager_headers)
    assert response.status_code == 200 and response.json()["status"] == "archived"
    timed_out = make_order(db, customer, tour, status=OrderStatus.CANCELLED)       # never paid
    assert client.post(f"{URL}/{timed_out.id}/archive", headers=manager_headers).status_code == 200
    assert client.post(f"{URL}/{timed_out.id}/archive", headers=manager_headers).status_code == 409


def test_rejected_order_is_archived_only_after_the_refund(client, db, manager, manager_headers, order):
    from app.models import Payment
    from app.models.enums import PaymentType, TransactionStatus

    take(client, manager_headers, order.id)
    reject(client, manager_headers, order.id)
    response = client.post(f"{URL}/{order.id}/archive", headers=manager_headers)
    assert response.status_code == 409 and "повернення коштів" in response.json()["detail"]
    [payment] = [p for p in order.payments if p.type == PaymentType.PAYMENT]
    db.add(Payment(order_id=order.id, type=PaymentType.REFUND, method=PaymentMethod.CARD,
                   status=TransactionStatus.PENDING, amount_uah=payment.paid_amount,
                   paid_amount=payment.paid_amount, refund_of_id=payment.id))
    db.flush()
    assert client.post(f"{URL}/{order.id}/archive", headers=manager_headers).status_code == 409  # pending
    db.scalars(select(Payment).where(Payment.type == PaymentType.REFUND)).one().status = TransactionStatus.SUCCEEDED
    db.flush()
    assert client.post(f"{URL}/{order.id}/archive", headers=manager_headers).status_code == 200


# ---------- access
@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.FINANCE, UserRole.ADMIN])
def test_manager_endpoints_only_for_managers(client, db, order, role):
    headers = headers_for(make_user(db, role=role))
    assert client.get(URL, headers=headers).status_code == 403
    assert client.get(f"{URL}/{order.id}", headers=headers).status_code == 403
    assert take(client, headers, order.id).status_code == 403
    assert confirm(client, headers, order.id).status_code == 403
    assert client.post(f"{URL}/{order.id}/archive", headers=headers).status_code == 403
    assert client.get(URL).status_code == 401
    assert take(client, {}, order.id).status_code == 401
