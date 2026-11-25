"""Spec 10: tour actions with reasons, locked fields, bookings on unpublish / archive, restore,
the back-office list and the form rules."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, Order, OrderStatusHistory, Payment, Tour
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus, PaymentType, TourStatus, \
    TransactionStatus
from app.services import clock
from app.services.order_expiry import expire_orders
from app.services.tours import LOCKED_FIELDS
from tests.factories import (city, country, error_text, make_active_tour, make_hotel, make_order,
                             make_tour, make_user, resort, tourist, years_before)
from tests.test_payments import event, send, stripe_gw  # noqa: F401  (fixture)

URL = "/api/manager/tours"
NOW = datetime.now(timezone.utc)


def get(client, headers, tour_id):
    response = client.get(f"{URL}/{tour_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def actions(body) -> dict[str, tuple[bool, str | None]]:
    return {a["action"]: (a["allowed"], a["reason"]) for a in body["tour_actions"]}


def booking(db, tour, status=OrderStatus.AWAITING_PAYMENT, minutes=20, **overrides):
    """A booking of 2 adults whose hold runs out in `minutes` (negative: already ran out)."""
    return make_order(db, make_user(db), tour, status=status,
                      hold_expires_at=NOW + timedelta(minutes=minutes), **overrides)


def mark_paid_once(db, order):
    """History says the order was paid (it may be cancelled and refunded since)."""
    db.add(OrderStatusHistory(order_id=order.id, old_status="awaiting_payment", new_status="paid"))
    db.flush()


# ---------- actions
def test_actions_of_a_ready_draft(client, db, manager, manager_headers):
    tour = make_active_tour(db, manager, status=TourStatus.DRAFT)
    assert actions(get(client, manager_headers, tour.id)) == {
        "edit": (True, None), "publish": (True, None), "archive": (True, None), "copy": (True, None)}


def test_actions_of_an_active_tour_use_the_endpoint_texts(client, db, manager, manager_headers):
    tour = make_active_tour(db, manager)
    body = get(client, manager_headers, tour.id)
    acts = actions(body)
    assert set(acts) == {"edit", "unpublish", "archive", "copy"}
    allowed, reason = acts["edit"]
    assert not allowed
    patch = client.patch(f"{URL}/{tour.id}", json={"nights": 5}, headers=manager_headers)
    assert (patch.status_code, error_text(patch)) == (409, reason)
    assert body["for_sale"] is True


def test_actions_of_an_archived_tour(client, db, manager, manager_headers):
    tour = make_tour(db, manager, status=TourStatus.ARCHIVED)
    assert actions(get(client, manager_headers, tour.id)) == {"restore": (True, None), "copy": (True, None)}


def test_publish_refusal_equals_the_endpoint_text(client, db, manager, manager_headers):
    tour = make_tour(db, manager, departure_from=clock.today() - timedelta(days=5),
                     departure_to=clock.today())          # the last start day is today: not bookable
    allowed, reason = actions(get(client, manager_headers, tour.id))["publish"]
    assert not allowed and "минули" in reason
    response = client.post(f"{URL}/{tour.id}/publish", headers=manager_headers)
    assert (response.status_code, error_text(response)) == (422, reason)
    assert response.json()["detail"][0]["loc"] == ["body", "departure_to"]


# ---------- restore
def test_restore_returns_an_archived_tour_to_draft_with_audit(client, db, manager, manager_headers):
    tour = make_tour(db, manager, status=TourStatus.ARCHIVED)
    response = client.post(f"{URL}/{tour.id}/restore", headers=manager_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "draft"
    [row] = db.scalars(select(AuditLog).where(AuditLog.entity == "tour",
                                              AuditLog.entity_id == str(tour.id))).all()
    assert (row.old_value, row.new_value, row.user_id) == ({"status": "archived"}, {"status": "draft"},
                                                           manager.id)


@pytest.mark.parametrize("start,action", [(TourStatus.DRAFT, "restore"), (TourStatus.ACTIVE, "restore"),
                                          (TourStatus.ARCHIVED, "unpublish")])
def test_restore_and_unpublish_only_from_their_status(client, db, manager, manager_headers, start, action):
    tour = make_tour(db, manager, status=start)
    response = client.post(f"{URL}/{tour.id}/{action}", headers=manager_headers)
    assert response.status_code == 409
    assert "Неможливо змінити статус" in error_text(response)


# ---------- locked fields
def test_no_locks_without_bookings(client, db, manager, manager_headers):
    assert get(client, manager_headers, make_tour(db, manager).id)["locked_fields"] == []


@pytest.mark.parametrize("final_status", [OrderStatus.PAID, OrderStatus.CANCELLED, OrderStatus.ARCHIVED])
def test_fields_locked_once_an_order_was_paid(client, db, manager, manager_headers, final_status):
    tour = make_tour(db, manager)
    order = make_order(db, make_user(db), tour, status=final_status)   # refunded or archived too
    mark_paid_once(db, order)
    body = get(client, manager_headers, tour.id)
    assert [f["field"] for f in body["locked_fields"]] == list(LOCKED_FIELDS)
    reason = body["locked_fields"][0]["reason"]
    assert "оплачені замовлення" in reason

    other_hotel = make_hotel(db, name="Інший")
    for change in ({"hotel_id": other_hotel.id}, {"title_uk": "Нова назва"}, {"nights": 5},
                   {"departure_to": (tour.departure_to + timedelta(days=1)).isoformat()},
                   {"meal_plan": "ai"}, {"transport_type": "bus", "departure_city_id": city(db, "Kyiv").id}):
        response = client.patch(f"{URL}/{tour.id}", json=change, headers=manager_headers)
        assert response.status_code == 409, change
        [issue] = response.json()["detail"]
        assert (issue["msg"], issue["type"]) == (reason, "tour_rule")
        assert issue["loc"][0] == "body" and issue["loc"][1] in LOCKED_FIELDS
    # The same values (the editor PATCHes the whole form) and prices are accepted.
    response = client.patch(f"{URL}/{tour.id}", json={
        "title_uk": f"  {tour.title_uk} ", "hotel_id": tour.hotel_id, "nights": tour.nights,
        "base_price": "999.00", "child_price": "100.00", "description": "Новий опис"},
        headers=manager_headers)
    assert response.status_code == 200, response.text
    assert response.json()["base_price"] == "999.00"


def test_unpaid_cancelled_or_abandoned_orders_do_not_lock(client, db, manager, manager_headers):
    tour = make_tour(db, manager)
    make_order(db, make_user(db), tour, status=OrderStatus.CANCELLED)
    booking(db, tour, minutes=-1)                        # hold ran out, not cancelled yet
    assert get(client, manager_headers, tour.id)["locked_fields"] == []


def test_fields_locked_while_a_hold_is_active_and_unlocked_after_expiry(client, db, manager,
                                                                          manager_headers):
    tour = make_tour(db, manager)
    order = booking(db, tour, status=OrderStatus.CHECKOUT, minutes=15)
    body = get(client, manager_headers, tour.id)
    assert body["active_bookings"] == 1
    assert body["locked_fields"][0]["reason"] == (
        "1 активних бронювань: дочекайтеся оплати або закінчення утримання")
    response = client.patch(f"{URL}/{tour.id}", json={"nights": 5}, headers=manager_headers)
    assert response.status_code == 409
    assert response.json()["detail"][0]["loc"] == ["body", "nights"]

    order.hold_expires_at = NOW - timedelta(seconds=1)   # the hold ran out
    db.flush()
    assert get(client, manager_headers, tour.id)["locked_fields"] == []
    assert client.patch(f"{URL}/{tour.id}", json={"nights": 5},
                        headers=manager_headers).status_code == 200


def test_partly_paid_transfer_locks_even_after_its_hold(client, db, manager, manager_headers):
    tour = make_tour(db, manager)
    booking(db, tour, minutes=-60, payment_status=PaymentStatus.PARTIALLY_PAID)
    body = get(client, manager_headers, tour.id)
    assert (body["active_bookings"], len(body["locked_fields"])) == (1, len(LOCKED_FIELDS))


# ---------- quota
def test_quota_cannot_drop_below_sold_plus_held(client, db, manager, manager_headers):
    tour = make_tour(db, manager, seats_total=10, seats_sold=3)
    booking(db, tour, minutes=10)                        # 2 seats held
    booking(db, tour, minutes=-1)                        # expired: not counted
    assert get(client, manager_headers, tour.id)["seats_held"] == 2
    response = client.patch(f"{URL}/{tour.id}", json={"seats_total": 4}, headers=manager_headers)
    assert response.status_code == 422
    [issue] = response.json()["detail"]
    assert issue["loc"] == ["body", "seats_total"]
    assert issue["msg"] == "Квота не може бути меншою за 5: продано 3, утримано в активних бронюваннях 2"
    assert client.patch(f"{URL}/{tour.id}", json={"seats_total": 5},
                        headers=manager_headers).status_code == 200


# ---------- unpublish keeps bookings payable
def test_unpublish_keeps_awaiting_payment_payable(client, db, manager, manager_headers, gateway):
    tour = make_active_tour(db, manager)
    customer = make_user(db)
    order = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT,
                       total_uah=Decimal("1000.00"), hold_expires_at=NOW + timedelta(minutes=20))
    body = client.post(f"{URL}/{tour.id}/unpublish", headers=manager_headers).json()
    assert (body["status"], body["active_bookings"]) == ("draft", 1)

    from tests.factories import headers_for
    response = client.post(f"/api/orders/{order.id}/pay", json={"method": "card"},
                           headers=headers_for(customer))
    assert response.status_code == 200, response.text
    assert response.json()["checkout_url"]
    db.expire_all()
    assert db.get(Order, order.id).status == OrderStatus.AWAITING_PAYMENT


def test_unpublished_tour_takes_no_new_bookings_but_an_old_checkout_can_be_confirmed(
        client, db, manager, manager_headers):
    from tests.factories import headers_for

    start = clock.today() + timedelta(days=12)
    tour = make_active_tour(db, manager, days_ahead=10)
    customer = make_user(db)
    headers = headers_for(customer)
    created = client.post("/api/orders", json={
        "tour_id": tour.id, "start_date": start.isoformat(), "adults": 1, "children": 0,
        "tourists": [tourist(years_before(start, 35))]}, headers=headers)
    assert created.status_code == 201, created.text
    client.post(f"{URL}/{tour.id}/unpublish", headers=manager_headers)

    again = client.post("/api/orders", json={"tour_id": tour.id, "start_date": start.isoformat(),
                                             "adults": 1, "children": 0}, headers=headers)
    assert again.status_code == 422                    # no new bookings
    confirmed = client.post(f"/api/orders/{created.json()['id']}/confirm",
                            json={"accept_offer": True}, headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "awaiting_payment"


def test_card_payment_after_unpublish_makes_the_order_paid(client, db, manager, manager_headers,
                                                           stripe_gw):
    tour = make_active_tour(db, manager)
    order = booking(db, tour, total_uah=Decimal("1000.00"))
    payment = card_payment_of(db, order)
    client.post(f"{URL}/{tour.id}/unpublish", headers=manager_headers)
    assert send(client, event(payment)).json()["result"] == "paid"
    db.expire_all()
    assert db.get(Order, order.id).status == OrderStatus.PAID
    # Now the paid order keeps the fields locked.
    assert "оплачені" in get(client, manager_headers, tour.id)["locked_fields"][0]["reason"]


def card_payment_of(db, order):
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                      status=TransactionStatus.PENDING, amount_uah=order.total_uah,
                      stripe_session_id=f"cs_test_{order.id}")
    db.add(payment)
    db.flush()
    return payment


# ---------- archive cancels unpaid bookings
def test_archive_cancels_unpaid_bookings_notifies_and_audits(client, db, manager, manager_headers,
                                                              stripe_gw):
    tour = make_active_tour(db, manager)
    checkout = booking(db, tour, status=OrderStatus.CHECKOUT)
    awaiting = booking(db, tour)
    expired = booking(db, tour, minutes=-5)                  # the job has not cancelled it yet
    payment = card_payment_of(db, awaiting)
    paid = make_order(db, make_user(db), tour, status=OrderStatus.PAID)
    assert get(client, manager_headers, tour.id)["archive_cancels"] == 3

    response = client.post(f"{URL}/{tour.id}/archive", headers=manager_headers)
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["archive_cancels"]) == ("archived", 0)
    db.expire_all()
    for order in (checkout, awaiting, expired):
        order = db.get(Order, order.id)
        assert order.status == OrderStatus.CANCELLED
        last = order.history[-1]
        assert (last.new_status, last.changed_by, last.comment) == ("cancelled", manager.id,
                                                                    "Тур знято з продажу")
        [note] = db.scalars(select(Notification).where(Notification.user_id == order.client_id)).all()
        assert note.title == f"Замовлення {order.number} скасовано"
        assert note.body.startswith("Тур знято з продажу.")
    assert db.get(Order, paid.id).status == OrderStatus.PAID     # paid orders stay
    assert stripe_gw.expired == [payment.stripe_session_id]       # open session closed
    assert db.get(Payment, payment.id).status == TransactionStatus.FAILED
    row = db.scalar(select(AuditLog).where(AuditLog.entity == "tour", AuditLog.entity_id == str(tour.id)))
    assert row.new_value["status"] == "archived"
    assert set(row.new_value["cancelled_orders"]) == {checkout.number, awaiting.number, expired.number}


def test_late_stripe_payment_after_archive_is_refunded(client, db, manager, manager_headers, stripe_gw):
    tour = make_active_tour(db, manager)
    order = booking(db, tour, total_uah=Decimal("1000.00"))
    payment = card_payment_of(db, order)
    client.post(f"{URL}/{tour.id}/archive", headers=manager_headers)
    # The client finished paying in the last second: Stripe still sends the completed event.
    assert send(client, event(payment)).json()["result"] == "refunded"
    assert len(stripe_gw.refunds) == 1
    db.expire_all()
    late = db.get(Order, order.id)
    assert (late.status, late.payment_status) == (OrderStatus.CANCELLED, PaymentStatus.REFUNDED)
    assert db.get(Tour, tour.id).seats_sold == 0


def test_archive_refused_while_a_transfer_is_partly_paid(client, db, manager, manager_headers):
    tour = make_active_tour(db, manager)
    booking(db, tour, payment_status=PaymentStatus.PARTIALLY_PAID)
    allowed, reason = actions(get(client, manager_headers, tour.id))["archive"]
    assert not allowed and "частково оплачено" in reason
    response = client.post(f"{URL}/{tour.id}/archive", headers=manager_headers)
    assert (response.status_code, error_text(response)) == (409, reason)
    assert db.get(Tour, tour.id).status == TourStatus.ACTIVE


def test_expiry_job_and_archive_do_not_cancel_twice(client, db, manager, manager_headers):
    tour = make_active_tour(db, manager)
    order = booking(db, tour, minutes=-1)
    assert expire_orders(db) == 1
    client.post(f"{URL}/{tour.id}/archive", headers=manager_headers)
    db.expire_all()
    assert [h.new_status for h in db.get(Order, order.id).history].count("cancelled") == 1


# ---------- field errors
@pytest.mark.parametrize("override,loc", [
    ({"nights": 0}, ["body", "nights"]),
    ({"base_price": "0"}, ["body", "base_price"]),
    ({"seats_total": 0}, ["body", "seats_total"]),
    ({"included": ["x" * 201]}, ["body", "included"]),
    ({"program_days": [{"day_number": 1, "description": "a"}, {"day_number": 2, "description": " "}]},
     ["body", "program_days", 1, "description"]),
])
def test_field_errors_name_the_field(client, db, manager_headers, override, loc):
    start = clock.today() + timedelta(days=30)
    body = {"title_en": "Test", "hotel_id": make_hotel(db).id, "transport_type": "none",
            "departure_from": start.isoformat(), "departure_to": start.isoformat(), "nights": 7,
            "seats_total": 10, "base_price": "100.00", "currency": "EUR"} | override
    response = client.post(URL, json=body, headers=manager_headers)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == loc


# ---------- list and rules
def test_list_filters_columns_and_sort(client, db, manager, manager_headers):
    antalya = make_hotel(db, name="Antalya Hotel", resort_en="Antalya")
    tour = make_active_tour(db, manager, hotel_id=antalya.id, title_uk="Анталія", seats_total=10)
    booking(db, tour)                                        # 2 seats held
    other = make_tour(db, manager, title_uk="Інший", departure_from=clock.today() + timedelta(days=200),
                      departure_to=clock.today() + timedelta(days=210),
                      hotel_id=make_hotel(db, resort_en="Hurghada").id)

    body = client.get(URL, params={"country_id": country(db, "TR").id}, headers=manager_headers).json()
    assert [item["id"] for item in body["items"]] == [tour.id]
    item = body["items"][0]
    assert (item["hotel_name"], item["resort_name"], item["country_name"]) == (
        "Antalya Hotel", "Анталія", "Туреччина")
    assert (item["free_seats"], item["seats_total"], item["image_url"]) == (8, 10, None)
    assert item["nearest_start"] == tour.departure_from.isoformat()
    assert item["for_sale"] is True and {a["action"] for a in item["tour_actions"]} >= {"unpublish"}

    assert [i["id"] for i in client.get(URL, params={"resort_id": resort(db, "Hurghada").id},
                                        headers=manager_headers).json()["items"]] == [other.id]
    period = {"departure_from": (clock.today() + timedelta(days=195)).isoformat(),
              "departure_to": (clock.today() + timedelta(days=201)).isoformat()}
    assert [i["id"] for i in client.get(URL, params=period, headers=manager_headers).json()["items"]] == [other.id]
    titles = [i["title_uk"] for i in client.get(URL, params={"sort": "title_asc"},
                                                headers=manager_headers).json()["items"]]
    assert titles == ["Анталія", "Інший"]
    dates = client.get(URL, params={"sort": "departure_asc"}, headers=manager_headers).json()["items"]
    assert [i["id"] for i in dates] == [tour.id, other.id]


def test_nearest_start_skips_past_dates(client, db, manager, manager_headers):
    tour = make_tour(db, manager, departure_from=clock.today() - timedelta(days=3),
                     departure_to=clock.today() + timedelta(days=3))
    past = make_tour(db, manager, departure_from=clock.today() - timedelta(days=9),
                     departure_to=clock.today())
    items = {i["id"]: i for i in client.get(URL, headers=manager_headers).json()["items"]}
    assert items[tour.id]["nearest_start"] == clock.tomorrow().isoformat()
    assert items[past.id]["nearest_start"] is None


def test_rules_endpoint(client, manager_headers):
    body = client.get(f"{URL}/rules", headers=manager_headers).json()
    assert body["photos"] == {"max_files": 20, "max_file_mb": 5, "file_types": ["jpg", "png"]}
    assert (body["max_title"], body["max_description"], body["max_day_text"]) == (200, 5000, 2000)
    assert (body["min_nights"], body["max_nights"], body["max_list_items"],
            body["max_list_item_length"]) == (1, 30, 20, 200)


# ---------- archived references
def test_a_draft_keeps_its_archived_hotel_on_edit_but_cannot_publish(client, db, manager, manager_headers):
    from app.models import Hotel

    tour = make_active_tour(db, manager, status=TourStatus.DRAFT)
    db.get(Hotel, tour.hotel_id).is_archived = True
    other_archived = make_hotel(db, name="Old one", is_archived=True)
    db.flush()
    response = client.patch(f"{URL}/{tour.id}", json={"base_price": "999.00", "hotel_id": tour.hotel_id},
                            headers=manager_headers)
    assert response.status_code == 200, response.text
    response = client.patch(f"{URL}/{tour.id}", json={"hotel_id": other_archived.id}, headers=manager_headers)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "hotel_id"]
    allowed, reason = actions(get(client, manager_headers, tour.id))["publish"]
    assert not allowed and "в архіві" in reason
