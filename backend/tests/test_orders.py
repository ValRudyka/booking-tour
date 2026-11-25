"""Client checkout: create, edit, confirm, cancel, hold timer, access (ТЗ 4.5.3, form 4.6.1.2)."""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import InsuranceType, Order, Setting
from app.models.enums import Currency, OrderStatus, TourStatus, UserRole
from app.services import clock
from tests.factories import (headers_for, make_active_tour, make_order, make_promo, make_user,
                             set_rate, tourist, years_before)

URL = "/api/orders"
START = clock.today() + timedelta(days=12)
ADULT = years_before(START, 35)
CHILD = years_before(START, 6)


@pytest.fixture()
def tour(db, manager):
    """EUR tour: adult 800, child 400, 7 nights, 10 seats; departures today+10 .. today+24."""
    return make_active_tour(db, manager, days_ahead=10, base_price=Decimal("800"),
                            child_price=Decimal("400"), currency=Currency.EUR, nights=7)


def create(client, headers, tour, adults=2, children=0, expected=201, **extra):
    body = {"tour_id": tour.id, "start_date": START.isoformat(), "adults": adults,
            "children": children} | extra
    response = client.post(URL, json=body, headers=headers)
    assert response.status_code == expected, response.text
    return response.json()


def free_seats(client, tour_id):
    return client.get(f"/api/tours/{tour_id}").json()["free_seats"]


def two_tourists():
    return [tourist(ADULT, first="Taras"), tourist(years_before(START, 33), first="Olena",
                                                   passport="FX654321")]


# ---------- create
def test_create_order_holds_seats(client, db, customer, customer_headers, tour):
    before = datetime.now(timezone.utc)
    body = create(client, customer_headers, tour, adults=2, children=1)
    assert re.fullmatch(rf"TU-{clock.today().year}-\d{{6}}", body["number"])
    assert body["status"] == "checkout" and body["payment_status"] == "awaiting"
    assert body["end_date"] == (START + timedelta(days=7)).isoformat()
    assert body["total_uah"] == body["price"]["total_uah"] == "97050.00"
    assert body["rate_used"] == "48.0000"
    hold = datetime.fromisoformat(body["hold_expires_at"])
    assert timedelta(minutes=19) < hold - before < timedelta(minutes=21)    # default 20 min
    assert [(h["old_status"], h["new_status"], h["changed_by"]) for h in body["history"]] == [
        (None, "checkout", customer.id)]
    assert free_seats(client, tour.id) == 7


def test_order_numbers_are_unique_and_increasing(client, customer_headers, tour):
    first = create(client, customer_headers, tour, adults=1)["number"]
    second = create(client, customer_headers, tour, adults=1)["number"]
    assert int(second[-6:]) > int(first[-6:])


def test_hold_time_comes_from_settings(client, db, customer_headers, tour):
    db.get(Setting, "booking_timeout_min").value = 5
    db.flush()
    before = datetime.now(timezone.utc)
    hold = datetime.fromisoformat(create(client, customer_headers, tour)["hold_expires_at"])
    assert timedelta(minutes=4) < hold - before < timedelta(minutes=6)


def test_create_with_tourists_and_promo(client, db, customer_headers, tour):
    make_promo(db, code="SUMMER10", value="10")
    body = create(client, customer_headers, tour, tourists=two_tourists(), promo_code="summer10",
                  wishes=" Ранній заїзд ")
    assert [t["first_name_lat"] for t in body["tourists"]] == ["Taras", "Olena"]
    assert body["promo_code"] == "SUMMER10"
    assert (body["discount_uah"], body["total_uah"]) == ("7750.00", "69750.00")
    assert body["wishes"] == "Ранній заїзд"


@pytest.mark.parametrize("overrides,message", [
    ({"adults": 0}, "щонайменше один дорослий"),
    ({"start_date": clock.today().isoformat()}, "не раніше завтрашнього дня"),
    ({"start_date": (clock.today() + timedelta(days=5)).isoformat()}, "в межах"),
    ({"start_date": (clock.today() + timedelta(days=25)).isoformat()}, "в межах"),
    ({"tourists": [tourist(ADULT)]}, "має дорівнювати"),
    ({"adults": 1, "children": 1, "tourists": [tourist(ADULT), tourist(ADULT)]}, "дітей — 0"),
    ({"tourists": [tourist(ADULT, last="Шевченко"), tourist(ADULT)]}, "латиницею"),
    ({"tourists": [tourist(ADULT, passport="FX-1234"), tourist(ADULT)]}, "4–20 символів"),
])
def test_create_validation(client, customer_headers, tour, overrides, message):
    body = {"tour_id": tour.id, "start_date": START.isoformat(), "adults": 2, "children": 0}
    response = client.post(URL, json=body | overrides, headers=customer_headers)
    assert response.status_code == 422, response.text
    assert message in response.json()["detail"]


def test_passport_must_be_valid_6_months_after_return(client, customer_headers, tour):
    end = START + timedelta(days=7)
    short = tourist(ADULT, expiry=end + timedelta(days=150))              # < 6 months
    response = client.post(URL, json={"tour_id": tour.id, "start_date": START.isoformat(),
                                      "adults": 2, "tourists": [short, tourist(ADULT)]},
                           headers=customer_headers)
    assert response.status_code == 422
    assert "щонайменше 6 місяців" in response.json()["detail"]


@pytest.mark.parametrize("tour_status", [TourStatus.DRAFT, TourStatus.ARCHIVED])
def test_inactive_tour_cannot_be_booked(client, db, customer_headers, tour, tour_status):
    tour.status = tour_status
    db.flush()
    body = create(client, customer_headers, tour, expected=422)
    assert body["detail"] == "Тур недоступний для бронювання"


def test_not_enough_seats(client, db, customer_headers, tour):
    tour.seats_sold = 9
    db.flush()
    assert create(client, customer_headers, tour, adults=2, expected=409)["detail"] == \
        "Недостатньо вільних місць: залишилось 1"


# ---------- edit
def test_update_recalculates_but_keeps_hold_timer(client, db, customer_headers, tour):
    order = create(client, customer_headers, tour)
    extended = db.scalar(select(InsuranceType.id).where(InsuranceType.name_uk == "Розширене"))
    response = client.patch(f"{URL}/{order['id']}", headers=customer_headers,
                            json={"insurance_type_id": extended, "wishes": "Дитяче ліжечко"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["price"]["insurance_uah"] == "1400.00"
    assert body["total_uah"] == "78200.00"
    assert body["hold_expires_at"] == order["hold_expires_at"]
    assert body["wishes"] == "Дитяче ліжечко"


def test_update_tourists_and_numbers(client, customer_headers, tour):
    order = create(client, customer_headers, tour, adults=2)
    new = [tourist(ADULT), tourist(CHILD, first="Ivan", passport="FX000001")]
    body = client.patch(f"{URL}/{order['id']}", json={"adults": 1, "children": 1, "tourists": new},
                        headers=customer_headers).json()
    assert (body["adults"], body["children"], len(body["tourists"])) == (1, 1, 2)
    assert body["total_uah"] == "58300.00"     # (800 + 400) × 48 + 350 × 2
    # stored tourists no longer match if only the numbers change
    response = client.patch(f"{URL}/{order['id']}", json={"adults": 2, "children": 0},
                            headers=customer_headers)
    assert response.status_code == 422


def test_more_tourists_rechecks_free_seats(client, db, customer_headers, tour):
    tour.seats_total = 4
    db.flush()
    order = create(client, customer_headers, tour, adults=2)
    create(client, headers_for(make_user(db)), tour, adults=1)       # 1 seat left
    assert client.patch(f"{URL}/{order['id']}", json={"adults": 3},
                        headers=customer_headers).status_code == 200
    response = client.patch(f"{URL}/{order['id']}", json={"adults": 4}, headers=customer_headers)
    assert response.status_code == 409
    assert "не більше 3" in response.json()["detail"]
    assert client.patch(f"{URL}/{order['id']}", json={"adults": 1},
                        headers=customer_headers).status_code == 200
    assert free_seats(client, tour.id) == 2


def test_promo_can_be_added_and_removed(client, db, customer_headers, tour):
    make_promo(db, code="MINUS", value="10")
    order = create(client, customer_headers, tour)
    body = client.patch(f"{URL}/{order['id']}", json={"promo_code": "MINUS"},
                        headers=customer_headers).json()
    assert body["discount_uah"] == "7750.00"
    body = client.patch(f"{URL}/{order['id']}", json={"promo_code": None},
                        headers=customer_headers).json()
    assert (body["promo_code"], body["discount_uah"]) == (None, "0.00")


# ---------- confirm
def confirm(client, headers, order_id, accept=True):
    return client.post(f"{URL}/{order_id}/confirm", json={"accept_offer": accept}, headers=headers)


def test_confirm_freezes_price(client, db, customer, customer_headers, tour):
    order = create(client, customer_headers, tour, tourists=two_tourists())
    set_rate(db, Currency.EUR, "50.0000")                       # rate changed during checkout
    response = confirm(client, customer_headers, order["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "awaiting_payment"
    assert (body["rate_used"], body["total_uah"]) == ("50.0000", "80700.00")
    assert body["offer_accepted_at"] is not None
    assert body["hold_expires_at"] == order["hold_expires_at"]   # timer not reset
    assert [h["new_status"] for h in body["history"]] == ["checkout", "awaiting_payment"]
    assert body["history"][-1]["changed_by"] == customer.id

    set_rate(db, Currency.EUR, "60.0000")                       # after confirm: frozen
    db.get(InsuranceType, body["price"]["insurance_id"]).price_uah = Decimal("999")
    db.flush()
    after = client.get(f"{URL}/{order['id']}", headers=customer_headers).json()
    assert (after["rate_used"], after["total_uah"]) == ("50.0000", "80700.00")
    assert client.patch(f"{URL}/{order['id']}", json={"wishes": "x"},
                        headers=customer_headers).status_code == 409


def test_confirm_requires_offer_consent(client, db, customer_headers, tour):
    order = create(client, customer_headers, tour, tourists=two_tourists())
    response = confirm(client, customer_headers, order["id"], accept=False)
    assert response.status_code == 422
    assert response.json()["detail"] == "Потрібна згода з Договором публічної оферти"
    assert db.get(Order, order["id"]).offer_accepted_at is None


def test_confirm_requires_all_tourists(client, customer_headers, tour):
    order = create(client, customer_headers, tour)
    response = confirm(client, customer_headers, order["id"])
    assert response.status_code == 422
    assert "потрібно 2, внесено 0" in response.json()["detail"]


def test_confirm_revalidates_promo(client, db, customer_headers, tour):
    promo = make_promo(db, code="SHORT", value="10")
    order = create(client, customer_headers, tour, tourists=two_tourists(), promo_code="SHORT")
    promo.is_active = False
    db.flush()
    assert confirm(client, customer_headers, order["id"]).json()["detail"] == "Промокод неактивний"


def test_cannot_confirm_twice(client, customer_headers, tour):
    order = create(client, customer_headers, tour, tourists=two_tourists())
    assert confirm(client, customer_headers, order["id"]).status_code == 200
    assert confirm(client, customer_headers, order["id"]).status_code == 409


# ---------- cancel
@pytest.mark.parametrize("confirm_first", [False, True])
def test_cancel_unpaid_order_releases_seats(client, customer_headers, tour, confirm_first):
    order = create(client, customer_headers, tour, tourists=two_tourists())
    if confirm_first:
        confirm(client, customer_headers, order["id"])
    assert free_seats(client, tour.id) == 8
    response = client.post(f"{URL}/{order['id']}/cancel", headers=customer_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert response.json()["history"][-1]["comment"] == "Скасовано клієнтом"
    assert free_seats(client, tour.id) == 10
    again = client.post(f"{URL}/{order['id']}/cancel", headers=customer_headers)
    assert again.status_code == 409


def test_paid_order_is_not_cancelled_here(client, db, customer, customer_headers, tour):
    order = make_order(db, customer, tour, status=OrderStatus.PAID)
    assert client.post(f"{URL}/{order.id}/cancel", headers=customer_headers).status_code == 409


# ---------- hold timer
def expire(db, order_id):
    db.get(Order, order_id).hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()


@pytest.mark.parametrize("action", ["patch", "confirm"])
def test_expired_hold_cancels_order_on_next_action(client, db, customer_headers, tour, action):
    order = create(client, customer_headers, tour, tourists=two_tourists())
    expire(db, order["id"])
    assert free_seats(client, tour.id) == 10        # expired hold no longer counts
    if action == "patch":
        response = client.patch(f"{URL}/{order['id']}", json={"wishes": "x"}, headers=customer_headers)
    else:
        response = confirm(client, customer_headers, order["id"])
    assert response.status_code == 409
    assert "Час на оформлення замовлення минув" in response.json()["detail"]
    db.expire_all()
    cancelled = db.get(Order, order["id"])
    assert cancelled.status == OrderStatus.CANCELLED
    assert (cancelled.history[-1].changed_by, cancelled.history[-1].comment) == (
        None, "Час на оплату минув")


# ---------- my orders
def test_list_and_detail_only_own_orders(client, db, customer, customer_headers, tour):
    first = create(client, customer_headers, tour, adults=1)
    second = create(client, customer_headers, tour, adults=1)
    client.post(f"{URL}/{first['id']}/cancel", headers=customer_headers)
    make_order(db, make_user(db), tour)                       # someone else's

    body = client.get(URL, headers=customer_headers).json()
    assert body["total"] == 2
    assert [o["id"] for o in body["items"]] == [second["id"], first["id"]]   # newest first
    body = client.get(URL, params={"status": "cancelled"}, headers=customer_headers).json()
    assert [o["id"] for o in body["items"]] == [first["id"]]
    page = client.get(URL, params={"page_size": 1, "page": 2}, headers=customer_headers).json()
    assert [o["id"] for o in page["items"]] == [first["id"]]

    detail = client.get(f"{URL}/{first['id']}", headers=customer_headers).json()
    assert [h["new_status"] for h in detail["history"]] == ["checkout", "cancelled"]
    assert detail["tour_title_uk"] == tour.title_uk and detail["hotel_name"] == "Test Hotel"


# ---------- access
ENDPOINTS = [("post", f"{URL}/quote"), ("post", URL), ("get", URL), ("get", f"{URL}/1"),
             ("patch", f"{URL}/1"), ("post", f"{URL}/1/confirm"), ("post", f"{URL}/1/cancel")]


def test_guest_gets_401(client):
    for method, url in ENDPOINTS:
        assert client.request(method, url).status_code == 401, (method, url)


@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.FINANCE, UserRole.ADMIN])
def test_staff_gets_403(client, db, role):
    headers = headers_for(make_user(db, role=role))
    for method, url in ENDPOINTS:
        assert client.request(method, url, headers=headers).status_code == 403, (method, url)


def test_other_clients_order_is_404(client, db, customer_headers, tour):
    order = create(client, headers_for(make_user(db)), tour, adults=1)
    for method, path, body in [("get", "", None), ("patch", "", {"wishes": "x"}),
                               ("post", "/confirm", {"accept_offer": True}), ("post", "/cancel", None)]:
        response = client.request(method, f"{URL}/{order['id']}{path}", json=body,
                                  headers=customer_headers)
        assert response.status_code == 404, (method, path)
        assert response.json()["detail"] == "Замовлення не знайдено"
    assert db.get(Order, order["id"]).status == OrderStatus.CHECKOUT
