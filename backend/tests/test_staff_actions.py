"""Back office (spec 09): staff_actions, the order queue tabs and filters, hand-over list,
document rules and can_delete."""
from datetime import timedelta

import pytest

from app.config import settings
from app.models import Order, OrderDocument, Payment
from app.models.enums import (OrderDocumentType, OrderStatus, PaymentMethod, PaymentType,
                              TransactionStatus, UserRole)
from app.services import clock
from tests.factories import headers_for, make_active_tour, make_order, make_paid_order, make_user

URL = "/api/manager/orders"
PDF = b"%PDF-1.4\n% voucher\n" + b"0" * 300
DEADLINE = (clock.today() + timedelta(days=10)).isoformat()


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


@pytest.fixture()
def order(db, customer, tour):
    return make_paid_order(db, customer, tour, start_date=tour.departure_from,
                           end_date=tour.departure_from + timedelta(days=7))


@pytest.fixture()
def other_manager(db):
    user = make_user(db, role=UserRole.MANAGER)
    user.last_name, user.first_name = "Коваленко", "Олена"
    db.flush()
    return user


def detail(client, headers, order_id):
    response = client.get(f"{URL}/{order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def actions(body) -> dict[str, tuple[bool, str | None]]:
    return {a["action"]: (a["allowed"], a["reason"]) for a in body["staff_actions"]}


def add_doc(db, order, doc_type=OrderDocumentType.VOUCHER, by=None):
    doc = OrderDocument(order_id=order.id, doc_type=doc_type, file_path=f"orders/{order.id}/x.pdf",
                        uploaded_by=by or order.client_id)
    db.add(doc)
    db.flush()
    db.refresh(order, ["documents"])
    return doc


# ---------- staff_actions: the table of spec 09 §2
def test_paid_order_can_be_taken_and_assigned(client, manager_headers, order):
    assert actions(detail(client, manager_headers, order.id)) == {
        "take": (True, None), "assign": (True, None), "edit_comment": (True, None)}


def test_in_progress_allows_confirm_and_reject(client, manager_headers, order):
    client.post(f"{URL}/{order.id}/take", headers=manager_headers)
    assert actions(detail(client, manager_headers, order.id)) == {
        "confirm": (True, None), "reject": (True, None), "assign": (True, None),
        "edit_comment": (True, None)}


def test_confirmed_needs_a_voucher_for_documents_ready(client, db, manager, manager_headers, order):
    order.status, order.manager_id = OrderStatus.CONFIRMED, manager.id
    db.flush()
    found = actions(detail(client, manager_headers, order.id))
    assert found["upload_documents"] == (True, None)
    assert found["documents_ready"] == (False, "Спершу завантажте ваучер")
    response = client.post(f"{URL}/{order.id}/documents-ready", headers=manager_headers)
    assert response.status_code == 409 and response.json()["detail"] == "Спершу завантажте ваучер"
    add_doc(db, order, by=manager.id)
    assert actions(detail(client, manager_headers, order.id))["documents_ready"] == (True, None)


def test_upload_refused_when_the_limit_is_reached(client, db, manager, manager_headers, order, monkeypatch):
    monkeypatch.setattr(settings, "max_documents_per_order", 1)
    order.status, order.manager_id = OrderStatus.CONFIRMED, manager.id
    add_doc(db, order, by=manager.id)
    allowed, reason = actions(detail(client, manager_headers, order.id))["upload_documents"]
    assert not allowed and "не більше 1 документів" in reason


def test_cancel_requested_only_hand_over_and_comment(client, db, manager, manager_headers, order):
    order.status, order.manager_id = OrderStatus.CANCEL_REQUESTED, manager.id
    db.flush()
    assert set(actions(detail(client, manager_headers, order.id))) == {"assign", "edit_comment"}


def test_archive_waits_for_the_refund(client, db, manager, manager_headers, order):
    order.status, order.manager_id = OrderStatus.REJECTED, manager.id
    db.flush()
    found = actions(detail(client, manager_headers, order.id))
    assert found["archive"] == (False, "Архівувати можна після завершення повернення коштів клієнту")
    [payment] = order.payments
    db.add(Payment(order_id=order.id, type=PaymentType.REFUND, method=PaymentMethod.CARD,
                   status=TransactionStatus.SUCCEEDED, amount_uah=payment.paid_amount,
                   paid_amount=payment.paid_amount, refund_of_id=payment.id))
    db.flush()
    assert actions(detail(client, manager_headers, order.id))["archive"] == (True, None)


@pytest.mark.parametrize("status", [OrderStatus.CHECKOUT, OrderStatus.AWAITING_PAYMENT])
def test_unpaid_orders_have_only_the_comment(client, db, customer, tour, manager_headers, status):
    waiting = make_order(db, customer, tour, status=status)
    assert set(actions(detail(client, manager_headers, waiting.id))) == {"edit_comment"}


def test_archived_order_cannot_be_assigned(client, db, customer, tour, manager_headers, other_manager):
    archived = make_paid_order(db, customer, tour, status=OrderStatus.ARCHIVED)
    assert "assign" not in actions(detail(client, manager_headers, archived.id))
    response = client.post(f"{URL}/{archived.id}/assign", json={"manager_id": other_manager.id},
                           headers=manager_headers)
    assert response.status_code == 409


def test_unpaid_order_cannot_be_assigned(client, db, customer, tour, manager_headers, other_manager):
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT)
    response = client.post(f"{URL}/{waiting.id}/assign", json={"manager_id": other_manager.id},
                           headers=manager_headers)
    assert response.status_code == 409 and "оплачене" in response.json()["detail"]
    assert db.get(Order, waiting.id).manager_id is None


# ---------- two managers (spec 09 §6)
def test_second_manager_sees_who_owns_the_order(client, manager_headers, other_manager, order):
    other = headers_for(other_manager)
    assert actions(detail(client, other, order.id))["take"] == (True, None)    # both see «Взяти»
    assert client.post(f"{URL}/{order.id}/take", headers=manager_headers).status_code == 200
    late = client.post(f"{URL}/{order.id}/take", headers=other)
    assert late.status_code == 409 and "інший менеджер" in late.json()["detail"]
    found = actions(detail(client, other, order.id))
    assert set(found) == {"confirm", "reject", "assign", "edit_comment"}
    for allowed, reason in found.values():
        assert not allowed and reason.startswith("Замовлення веде інший менеджер (Шевченко Т.)")


def test_finance_gets_no_actions(client, db, order):
    finance = make_user(db, role=UserRole.FINANCE)
    body = client.get(f"/api/finance/orders/{order.id}", headers=headers_for(finance)).json()
    assert body["staff_actions"] == [] and body["internal_comment"] is None


# ---------- documents: can_delete, rules
def test_can_delete_follows_the_delete_rules(client, db, manager, manager_headers, other_manager, order):
    order.status, order.manager_id = OrderStatus.DOCUMENTS_READY, manager.id
    voucher = add_doc(db, order, by=manager.id)
    ticket = add_doc(db, order, OrderDocumentType.AIR_TICKET, by=manager.id)
    evidence = add_doc(db, order, OrderDocumentType.CANCEL_EVIDENCE)
    docs = {d["id"]: d["can_delete"] for d in detail(client, manager_headers, order.id)["documents"]}
    assert docs == {voucher.id: False, ticket.id: True, evidence.id: False}    # the last voucher
    others = detail(client, headers_for(other_manager), order.id)["documents"]
    assert not any(d["can_delete"] for d in others)


def test_document_rules(client, manager_headers):
    response = client.get(f"{URL}/document-rules", headers=manager_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "doc_types": ["voucher", "air_ticket", "insurance_policy", "info_sheet"],
        "max_documents": settings.max_documents_per_order, "max_file_mb": settings.max_document_mb,
        "file_types": ["jpg", "pdf", "png"]}


# ---------- the queue: tabs, counts, filters, sort
def test_queue_tabs_and_counts(client, db, customer, tour, manager, manager_headers, other_manager, order):
    mine = make_paid_order(db, customer, tour, status=OrderStatus.IN_PROGRESS, manager_id=manager.id)
    theirs = make_paid_order(db, customer, tour, status=OrderStatus.IN_PROGRESS, manager_id=other_manager.id)
    make_paid_order(db, customer, tour, status=OrderStatus.ARCHIVED, manager_id=manager.id)

    def queue(name):
        body = client.get(URL, params={"queue": name}, headers=manager_headers).json()
        return {i["id"] for i in body["items"]}, body["queue_counts"]

    new, counts = queue("new")
    assert new == {order.id} and counts == {"new": 1, "mine": 1, "all": 3}
    assert queue("mine")[0] == {mine.id}
    assert queue("all")[0] == {order.id, mine.id, theirs.id}
    # Counts ignore the search filters.
    body = client.get(URL, params={"queue": "new", "number": "nothing"}, headers=manager_headers).json()
    assert body["total"] == 0 and body["queue_counts"]["new"] == 1


def test_client_and_created_filters(client, db, tour, manager_headers):
    anna = make_user(db, phone="+380671112233", email="anna@example.com")
    anna.last_name, anna.first_name = "Мельник", "Анна"
    db.flush()
    hers = make_paid_order(db, anna, tour)
    others = make_paid_order(db, make_user(db), tour)

    def ids(**params):
        return {i["id"] for i in client.get(URL, params=params, headers=manager_headers).json()["items"]}

    for text in ("Мельник Анна", "анна", "0671112233", "ANNA@example"):
        assert ids(client=text) == {hers.id}, text
    others.created_at = clock.day_start(clock.today() - timedelta(days=5)) + timedelta(hours=1)
    db.flush()
    today = clock.today().isoformat()
    assert ids(created_from=today) == {hers.id}
    assert ids(created_to=(clock.today() - timedelta(days=5)).isoformat()) == {others.id}
    row = client.get(URL, params={"client": "Мельник"}, headers=manager_headers).json()["items"][0]
    assert row["client_phone"] == "+380671112233" and row["overdue"] is False


def test_sort_by_start_date(client, db, customer, manager, manager_headers):
    early = make_active_tour(db, manager, days_ahead=10)
    late = make_active_tour(db, manager, days_ahead=40)
    first = make_paid_order(db, customer, late, start_date=late.departure_from)
    second = make_paid_order(db, customer, early, start_date=early.departure_from)
    ids = lambda sort: [i["id"] for i in client.get(URL, params={"sort": sort},  # noqa: E731
                                                    headers=manager_headers).json()["items"]]
    assert ids("start_asc") == [second.id, first.id]
    assert ids("start_desc") == [first.id, second.id]
    assert ids("created_desc") == [second.id, first.id]
    assert client.get(URL, params={"sort": "price"}, headers=manager_headers).status_code == 422


def test_detail_names_services_places_and_history_authors(client, manager_headers, order):
    client.post(f"{URL}/{order.id}/take", headers=manager_headers)
    body = detail(client, manager_headers, order.id)
    assert body["country_name"] and body["resort_name"] and body["transport_type"]
    assert body["history"][-1]["changed_by_name"] == "Шевченко Т."


# ---------- the hand-over list
def test_managers_list(client, db, manager, manager_headers, other_manager):
    blocked = make_user(db, role=UserRole.MANAGER)
    blocked.is_active = False
    make_user(db, role=UserRole.FINANCE)
    db.flush()
    body = client.get("/api/manager/managers", headers=manager_headers).json()
    ids = [m["id"] for m in body]
    assert manager.id in ids and other_manager.id in ids and blocked.id not in ids
    assert {"id": other_manager.id, "name": "Коваленко Олена"} in body
    assert client.get("/api/manager/managers", headers=headers_for(make_user(db))).status_code == 403
