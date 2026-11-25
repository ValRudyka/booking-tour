"""Client cabinet read API (spec 06): «Мої замовлення» groups, client actions per status, tour
facts and the pending transfer on the order page, form rules for cancellation and reviews."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import settings
from app.models import OrderStatusHistory, Payment
from app.models.enums import (MealPlan, OrderStatus, PaymentMethod, PaymentStatus, PaymentType, ReviewStatus,
                              TourStatus, TransactionStatus, TransportType)
from app.services import app_settings
from tests.factories import (city, headers_for, make_active_tour, make_order, make_paid_order,
                             make_review, make_user)

NOW = datetime.now(timezone.utc)
S = OrderStatus


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager, seats_total=100)


def history(db, order, *statuses):
    for new in statuses:
        db.add(OrderStatusHistory(order_id=order.id, old_status=None, new_status=new))
    db.flush()


def order_in(db, customer, tour, status, *, confirmed=True, **overrides):
    """An order in `status`; `confirmed` = the client reached «Перейти до оплати»."""
    overrides.setdefault("offer_accepted_at", NOW if confirmed else None)
    if status in (S.CHECKOUT, S.AWAITING_PAYMENT):
        overrides.setdefault("hold_expires_at", NOW + timedelta(minutes=15))
        return make_order(db, customer, tour, status=status, **overrides)
    return make_paid_order(db, customer, tour, status=status, **overrides)


def listed(client, headers, **params):
    response = client.get("/api/orders", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [o["number"] for o in response.json()["items"]], response.json()["total"]


# ---------- groups
def test_groups_split_orders_and_hide_abandoned_bookings(client, db, customer, customer_headers, tour):
    active = [order_in(db, customer, tour, s) for s in
              (S.CHECKOUT, S.AWAITING_PAYMENT, S.PAID, S.IN_PROGRESS, S.CONFIRMED, S.DOCUMENTS_READY,
               S.CANCEL_REQUESTED)]
    completed = order_in(db, customer, tour, S.COMPLETED)
    archived_trip = order_in(db, customer, tour, S.ARCHIVED)
    history(db, archived_trip, S.COMPLETED, S.ARCHIVED)
    rejected = order_in(db, customer, tour, S.REJECTED)
    cancelled = order_in(db, customer, tour, S.CANCELLED)             # confirmed, then cancelled
    archived_cancelled = order_in(db, customer, tour, S.ARCHIVED)
    history(db, archived_cancelled, S.CANCELLED, S.ARCHIVED)
    abandoned = order_in(db, customer, tour, S.CANCELLED, confirmed=False,
                         payment_status=PaymentStatus.AWAITING)
    abandoned_archived = order_in(db, customer, tour, S.ARCHIVED, confirmed=False)
    other_client = make_user(db)
    order_in(db, other_client, tour, S.PAID)

    def numbers(orders):
        return sorted(o.number for o in orders)

    assert sorted(listed(client, customer_headers, group="active")[0]) == numbers(active)
    assert sorted(listed(client, customer_headers, group="completed")[0]) == numbers(
        [completed, archived_trip])
    assert sorted(listed(client, customer_headers, group="cancelled")[0]) == numbers(
        [rejected, cancelled, archived_cancelled])
    everything, total = listed(client, customer_headers, group="all")
    assert total == 12 and abandoned.number not in everything
    assert abandoned_archived.number not in everything
    # Without a group: the old behaviour (every order), used by the booking wizard.
    assert listed(client, customer_headers)[1] == 14


def test_group_pages_and_rejects_unknown_group(client, db, customer, customer_headers, tour):
    for _ in range(3):
        order_in(db, customer, tour, S.PAID)
    numbers, total = listed(client, customer_headers, group="active", page=2, page_size=2)
    assert (len(numbers), total) == (1, 3)
    assert client.get("/api/orders", params={"group": "old"}, headers=customer_headers).status_code == 422


# ---------- client actions: one row per status
@pytest.mark.parametrize(("status", "expected"), [
    (S.CHECKOUT, ["continue_checkout", "cancel"]),
    (S.AWAITING_PAYMENT, ["pay", "cancel"]),
    (S.PAID, ["cancel_request"]),
    (S.IN_PROGRESS, ["cancel_request"]),
    (S.CONFIRMED, ["cancel_request", "download_documents"]),
    (S.DOCUMENTS_READY, ["cancel_request", "download_documents"]),
    (S.COMPLETED, ["review", "download_documents"]),
    (S.REJECTED, []),
    (S.CANCEL_REQUESTED, []),
    (S.CANCELLED, []),
    (S.ARCHIVED, ["download_documents"]),   # archived without «Завершено»: no trip, no review
])
def test_client_actions_for_each_status(client, db, customer, customer_headers, tour, status, expected):
    order = order_in(db, customer, tour, status)
    detail = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert detail["client_actions"] == expected
    row = client.get("/api/orders", headers=customer_headers).json()["items"][0]
    assert row["client_actions"] == expected


def test_actions_follow_the_review_and_the_archive(client, db, customer, customer_headers, tour):
    order = order_in(db, customer, tour, S.ARCHIVED)
    history(db, order, S.COMPLETED, S.ARCHIVED)

    def actions():
        return client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["client_actions"]

    assert actions() == ["review", "download_documents"]
    make_review(db, order, status=ReviewStatus.PENDING)
    assert actions() == ["view_review", "download_documents"]


def test_no_actions_once_the_hold_ran_out(client, db, customer, customer_headers, tour):
    order = order_in(db, customer, tour, S.AWAITING_PAYMENT, hold_expires_at=NOW - timedelta(minutes=1))
    assert client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["client_actions"] == []


def test_partly_paid_transfer_can_be_paid_but_not_cancelled(client, db, customer, customer_headers, tour):
    order = order_in(db, customer, tour, S.AWAITING_PAYMENT, payment_status=PaymentStatus.PARTIALLY_PAID,
                     hold_expires_at=NOW - timedelta(hours=1))   # never runs out once money came
    body = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert body["client_actions"] == ["pay"]
    # The action list and the endpoint agree.
    assert client.post(f"/api/orders/{order.id}/cancel", headers=customer_headers).status_code == 409


def test_each_refused_action_is_refused_by_its_endpoint(client, db, customer, customer_headers, tour):
    """A status without an action gets 409 from that action's endpoint (same checks)."""
    order = order_in(db, customer, tour, S.CANCEL_REQUESTED)
    headers = customer_headers
    assert client.post(f"/api/orders/{order.id}/pay", json={"method": "card"}, headers=headers).status_code == 409
    assert client.post(f"/api/orders/{order.id}/cancel", headers=headers).status_code == 409
    assert client.post(f"/api/orders/{order.id}/cancel-request", headers=headers, data={
        "reason_code": "illness", "accept_penalty_policy": "true"}).status_code == 409
    assert client.post(f"/api/orders/{order.id}/review", headers=headers, data={
        "hotel_rating": "5", "service_rating": "5"}).status_code == 409


# ---------- order page facts
def test_order_page_has_tour_facts_and_sale_flag(client, db, customer, customer_headers, manager):
    kyiv = city(db, "Kyiv")
    tour = make_active_tour(db, manager, transport_type=TransportType.AIR, departure_city_id=kyiv.id,
                            meal_plan=MealPlan.AI)
    order = order_in(db, customer, tour, S.PAID)
    body = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert body["tour_for_sale"] is True
    assert (body["country_name"], body["resort_name"]) == ("Туреччина", "Анталія")
    assert (body["departure_city_name"], body["transport_type"], body["meal_plan"]) == ("Київ", "air", "ai")
    assert body["pending_transfer"] is None

    tour.status = TourStatus.ARCHIVED
    db.flush()
    assert client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["tour_for_sale"] is False


def test_tour_not_for_sale_on_its_last_start_day(client, db, customer, customer_headers, manager):
    from app.services import clock
    tour = make_active_tour(db, manager, days_ahead=-10, departure_to=clock.today())
    order = order_in(db, customer, tour, S.PAID)
    assert client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["tour_for_sale"] is False


def test_pending_transfer_details_are_shown_again(client, db, customer, customer_headers, tour):
    order = order_in(db, customer, tour, S.AWAITING_PAYMENT, total_uah=Decimal("77000.00"))
    paid = client.post(f"/api/orders/{order.id}/pay", json={"method": "bank_transfer"},
                       headers=customer_headers).json()
    body = client.get(f"/api/orders/{order.id}", headers=customer_headers).json()
    assert body["pending_transfer"] == paid["bank_details"]
    assert body["pending_transfer"]["iban"] == settings.bank_iban

    # Once finance confirms it, nothing is pending any more.
    payment = db.get(Payment, paid["payment"]["id"])
    payment.status, payment.paid_amount = TransactionStatus.SUCCEEDED, payment.amount_uah
    db.flush()
    assert client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["pending_transfer"] is None


def test_card_payment_is_not_a_pending_transfer(client, db, customer, customer_headers, tour):
    order = order_in(db, customer, tour, S.AWAITING_PAYMENT)
    db.add(Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                   status=TransactionStatus.PENDING, amount_uah=Decimal("77000.00")))
    db.flush()
    assert client.get(f"/api/orders/{order.id}", headers=customer_headers).json()["pending_transfer"] is None


# ---------- form rules from the server
def test_cancel_request_form_limits(client, db, customer, customer_headers, tour, monkeypatch):
    monkeypatch.setattr(settings, "max_cancel_evidence_files", 3)
    monkeypatch.setattr(settings, "max_document_mb", 7)
    order = order_in(db, customer, tour, S.PAID)
    body = client.get(f"/api/orders/{order.id}/cancel-request", headers=customer_headers).json()
    assert body == {"evidence": {"max_files": 3, "max_file_mb": 7, "file_types": ["jpg", "pdf"]}}


def test_review_state_of_an_order(client, db, customer, customer_headers, tour, monkeypatch):
    monkeypatch.setattr(settings, "max_review_photos", 4)
    order = order_in(db, customer, tour, S.COMPLETED)
    body = client.get(f"/api/orders/{order.id}/review", headers=customer_headers).json()
    assert body == {"can_write": True, "premoderation": True,
                    "photos": {"max_files": 4, "max_file_mb": settings.max_review_photo_mb,
                               "file_types": ["jpg", "png"]},
                    "review": None}

    review = make_review(db, order, status=ReviewStatus.REJECTED, reject_reason="Лайка")
    body = client.get(f"/api/orders/{order.id}/review", headers=customer_headers).json()
    assert body["can_write"] is False
    assert (body["review"]["id"], body["review"]["status"], body["review"]["can_resubmit"]) == (
        review.id, "rejected", True)


def test_review_state_shows_the_premoderation_setting(client, db, customer, customer_headers, tour,
                                                      monkeypatch):
    monkeypatch.setattr("app.routers.reviews.review_premoderation", lambda db: False)
    order = order_in(db, customer, tour, S.PAID)
    body = client.get(f"/api/orders/{order.id}/review", headers=customer_headers).json()
    assert (body["can_write"], body["premoderation"]) == (False, False)


def test_form_rules_of_someone_elses_order_are_404(client, db, customer, tour):
    order = order_in(db, customer, tour, S.COMPLETED)
    stranger = headers_for(make_user(db))
    assert client.get(f"/api/orders/{order.id}/review", headers=stranger).status_code == 404
    assert client.get(f"/api/orders/{order.id}/cancel-request", headers=stranger).status_code == 404


def test_premoderation_helper_is_the_setting(db):
    assert app_settings.review_premoderation(db) is True
