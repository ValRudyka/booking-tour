"""In-app notifications: created by change_status(), listed and read by their owner only."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification
from app.models.enums import OrderStatus, UserRole
from app.services.notifications import notify, notify_finance, notify_managers
from app.services.order_expiry import expire_orders
from app.services.order_status import change_status
from tests.factories import headers_for, make_active_tour, make_order, make_user

NOW = datetime.now(timezone.utc)
URL = "/api/me/notifications"


@pytest.fixture()
def order(db, customer, manager):
    return make_order(db, customer, make_active_tour(db, manager), status=OrderStatus.AWAITING_PAYMENT,
                      hold_expires_at=NOW + timedelta(minutes=20))


def notes_of(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id)).all()


def test_status_changes_notify_the_client(db, customer, manager, order):
    change_status(db, order, OrderStatus.PAID, None)
    change_status(db, order, OrderStatus.IN_PROGRESS, manager)          # no message for this one
    order.pnr = "ABC123"
    change_status(db, order, OrderStatus.CONFIRMED, manager, client_message="Виліт о 06:00")
    titles = [n.title for n in notes_of(db, customer)]
    assert titles == [f"Замовлення {order.number} оплачено",
                      f"Бронювання {order.number} підтверджено"]
    confirmed = notes_of(db, customer)[-1]
    assert "ABC123" in confirmed.body and confirmed.body.endswith("Повідомлення менеджера: Виліт о 06:00")
    assert confirmed.order_id == order.id and confirmed.is_read is False


def test_timeout_notifies_but_own_cancel_does_not(client, db, customer, customer_headers, manager, order):
    order.hold_expires_at = NOW - timedelta(minutes=1)
    expire_orders(db)
    [note] = notes_of(db, customer)
    assert note.title == f"Замовлення {order.number} скасовано"
    assert note.body.startswith("Час на оплату минув")

    other = make_order(db, customer, order.tour, status=OrderStatus.AWAITING_PAYMENT,
                       hold_expires_at=NOW + timedelta(minutes=20))
    assert client.post(f"/api/orders/{other.id}/cancel", headers=customer_headers).status_code == 200
    assert len(notes_of(db, customer)) == 1


def test_staff_notifications(db, manager, order):
    second_manager = make_user(db, role=UserRole.MANAGER)
    finance = make_user(db, role=UserRole.FINANCE)
    blocked = make_user(db, role=UserRole.FINANCE)
    blocked.is_active = False
    notify_managers(db, order, "Нове клопотання", "...")
    assert len(notes_of(db, manager)) == 1 and len(notes_of(db, second_manager)) == 1
    order.manager_id = manager.id
    notify_managers(db, order, "Ще одне", "...")
    assert len(notes_of(db, manager)) == 2 and len(notes_of(db, second_manager)) == 1
    notify_finance(db, order, "Повернення", "...")
    assert len(notes_of(db, finance)) == 1 and notes_of(db, blocked) == []


def test_list_read_and_privacy(client, db, customer, customer_headers):
    for i in range(3):
        notify(db, customer.id, f"Тема {i}", "Текст")
    stranger = notify(db, make_user(db).id, "Чуже", "Текст")

    page = client.get(URL, params={"page_size": 2}, headers=customer_headers).json()
    assert (page["total"], page["unread"]) == (3, 3)
    assert [n["title"] for n in page["items"]] == ["Тема 2", "Тема 1"]          # newest first

    first = page["items"][0]["id"]
    read = client.post(f"{URL}/{first}/read", headers=customer_headers)
    assert read.status_code == 200 and read.json()["is_read"] is True
    unread = client.get(URL, params={"unread_only": True}, headers=customer_headers).json()
    assert (unread["total"], unread["unread"]) == (2, 2)

    assert client.post(f"{URL}/{stranger.id}/read", headers=customer_headers).status_code == 404
    assert client.post(f"{URL}/999999/read", headers=customer_headers).status_code == 404
    assert client.post(f"{URL}/read-all", headers=customer_headers).json() == {"marked": 2}
    assert client.get(URL, headers=customer_headers).json()["unread"] == 0
    db.refresh(stranger)
    assert stranger.is_read is False


def test_staff_have_notifications_too_and_guests_none(client, db):
    finance = make_user(db, role=UserRole.FINANCE)
    notify(db, finance.id, "Нове повернення", "Текст")
    assert client.get(URL, headers=headers_for(finance)).json()["total"] == 1
    assert client.get(URL).status_code == 401
