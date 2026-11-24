"""Public catalog: visibility, filters, sorting, pagination, free seats, tour page."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import TourImage, TourProgramDay
from app.models.enums import Currency, OrderStatus, TourStatus, TransportType
from app.services import clock
from tests.factories import (city, country, make_active_tour, make_hotel, make_order, make_tour,
                             make_user, resort)

URL = "/api/tours"
TODAY = clock.today()


@pytest.fixture()
def catalog(db, manager):
    """Three public tours (rates: EUR 48, USD 42) plus three hidden ones."""
    rixos = make_hotel(db, name="Rixos", resort_en="Antalya", stars=5, rating=4.5)
    steigen = make_hotel(db, name="Steigenberger", resort_en="Hurghada", stars=4)
    budva = make_hotel(db, name="Budva Inn", resort_en="Budva", stars=3, rating=3.9)
    tours = {
        "antalya": make_active_tour(db, manager, days_ahead=30, title_en="Antalya", hotel_id=rixos.id,
                                    transport_type=TransportType.AIR,
                                    departure_city_id=city(db, "Warsaw").id, nights=7,
                                    base_price=Decimal("800"), currency=Currency.EUR,  # 38 400 грн
                                    is_featured=True),
        "hurghada": make_active_tour(db, manager, days_ahead=60, title_en="Hurghada",
                                     hotel_id=steigen.id, nights=10, base_price=Decimal("900"),
                                     currency=Currency.USD),                            # 37 800 грн
        "budva": make_active_tour(db, manager, days_ahead=10, title_en="Budva", hotel_id=budva.id,
                                  transport_type=TransportType.BUS,
                                  departure_city_id=city(db, "Kyiv").id, nights=5,
                                  base_price=Decimal("25000"), currency=Currency.UAH),  # 25 000 грн
    }
    make_tour(db, manager, title_en="Draft", hotel_id=rixos.id)
    make_active_tour(db, manager, title_en="Archived", hotel_id=rixos.id, status=TourStatus.ARCHIVED)
    make_active_tour(db, manager, title_en="Finished", hotel_id=rixos.id,
                     departure_from=TODAY - timedelta(days=10), departure_to=TODAY - timedelta(days=1))
    db.expire_all()  # read values back as the database stores them (e.g. 800 -> 800.00)
    return tours


def titles(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return [item["title_en"] for item in response.json()["items"]]


def test_guest_sees_only_active_current_tours(client, catalog):
    assert titles(client) == ["Budva", "Antalya", "Hurghada"]  # default: nearest date first


def test_card_content(client, catalog):
    card = client.get(URL, params={"q": "Rixos"}).json()["items"][0]
    assert card["price_from_uah"] == "38400.00"
    assert card["base_price"] == "800.00" and card["currency"] == "EUR"
    assert card["free_seats"] == 10
    assert card["country"]["iso_code"] == "TR"
    assert card["resort"]["name_en"] == "Antalya"
    assert card["hotel"] == {"id": card["hotel"]["id"], "resort_id": card["resort"]["id"],
                             "name": "Rixos", "stars": 5, "rating_avg": "4.50"}
    assert card["departure_city"]["name_en"] == "Warsaw"
    assert card["is_featured"] is True
    assert card["image_url"] is None


@pytest.mark.parametrize("params,expected", [
    ({"q": "steigen"}, ["Hurghada"]),
    ({"q": "budva"}, ["Budva"]),
    ({"q": "100%_"}, []),                                  # special characters are literal
    ({"transport_type": "bus"}, ["Budva"]),
    ({"transport_type": "air"}, ["Antalya"]),
    ({"nights_min": 7}, ["Antalya", "Hurghada"]),
    ({"nights_max": 7}, ["Budva", "Antalya"]),
    ({"nights_min": 6, "nights_max": 8}, ["Antalya"]),
    ({"price_min": 30000}, ["Antalya", "Hurghada"]),       # EUR and USD compared in UAH
    ({"price_max": 38000}, ["Budva", "Hurghada"]),
    ({"price_min": 37800, "price_max": 38400}, ["Antalya", "Hurghada"]),
    ({"stars": [5]}, ["Antalya"]),
    ({"stars": [3, 4]}, ["Budva", "Hurghada"]),
    ({"featured": True}, ["Antalya"]),
    ({"featured": False}, ["Budva", "Hurghada"]),
])
def test_filters(client, catalog, params, expected):
    assert titles(client, **params) == expected


def test_filters_by_ids(client, db, catalog):
    assert titles(client, country_id=country(db, "EG").id) == ["Hurghada"]
    assert titles(client, resort_id=resort(db, "Budva").id) == ["Budva"]
    assert titles(client, departure_city_id=city(db, "Warsaw").id) == ["Antalya"]


def test_date_filter_uses_range_overlap(client, catalog):
    # Antalya departures: today+30 .. today+44, Hurghada: +60 .. +74, Budva: +10 .. +24
    assert titles(client, date_from=(TODAY + timedelta(days=40)).isoformat(),
                  date_to=(TODAY + timedelta(days=50)).isoformat()) == ["Antalya"]
    assert titles(client, date_from=(TODAY + timedelta(days=70)).isoformat()) == ["Hurghada"]
    assert titles(client, date_to=(TODAY + timedelta(days=30)).isoformat()) == ["Budva", "Antalya"]


def test_combined_filters(client, catalog):
    assert titles(client, price_max=40000, nights_min=7, stars=[4, 5], sort="price_asc") == [
        "Hurghada", "Antalya"]


@pytest.mark.parametrize("sort,expected", [
    ("price_asc", ["Budva", "Hurghada", "Antalya"]),
    ("price_desc", ["Antalya", "Hurghada", "Budva"]),
    ("date_asc", ["Budva", "Antalya", "Hurghada"]),
    ("date_desc", ["Hurghada", "Antalya", "Budva"]),
    ("rating_desc", ["Antalya", "Budva", "Hurghada"]),     # no rating goes last
])
def test_sorting(client, catalog, sort, expected):
    assert titles(client, sort=sort) == expected


def test_pagination(client, catalog):
    first = client.get(URL, params={"page_size": 2, "sort": "price_asc"}).json()
    assert (first["total"], first["page"], first["page_size"]) == (3, 1, 2)
    second = client.get(URL, params={"page_size": 2, "page": 2, "sort": "price_asc"}).json()
    assert [i["title_en"] for i in first["items"] + second["items"]] == ["Budva", "Hurghada", "Antalya"]
    assert client.get(URL, params={"page": 3, "page_size": 2}).json()["items"] == []


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 51}, {"page_size": 0},
                                    {"sort": "name"}, {"nights_min": 0}, {"price_min": -1}])
def test_invalid_query(client, params):
    assert client.get(URL, params=params).status_code == 422


def test_free_seats_count_sold_and_unexpired_holds(client, db, manager, catalog):
    tour = catalog["antalya"]           # 10 seats
    tour.seats_sold = 3
    customer = make_user(db)
    now = datetime.now(timezone.utc)
    make_order(db, customer, tour, adults=2, children=1, status=OrderStatus.CHECKOUT,
               hold_expires_at=now + timedelta(minutes=15))                  # held: -3
    make_order(db, customer, tour, adults=1, status=OrderStatus.AWAITING_PAYMENT,
               hold_expires_at=now + timedelta(minutes=5))                   # held: -1
    make_order(db, customer, tour, adults=4, status=OrderStatus.CHECKOUT,
               hold_expires_at=now - timedelta(minutes=1))                   # expired: ignored
    make_order(db, customer, tour, adults=2, status=OrderStatus.PAID)        # counted in seats_sold
    db.flush()
    card = client.get(URL, params={"q": "Rixos"}).json()["items"][0]
    assert card["free_seats"] == 10 - 3 - 3 - 1
    assert client.get(f"{URL}/{tour.id}").json()["free_seats"] == 3


def test_has_seats_hides_sold_out(client, db, catalog):
    catalog["budva"].seats_sold = catalog["budva"].seats_total
    db.flush()
    assert titles(client, has_seats=True) == ["Antalya", "Hurghada"]
    assert titles(client, has_seats=False) == ["Budva"]
    sold_out = client.get(URL, params={"q": "budva"}).json()["items"][0]
    assert sold_out["free_seats"] == 0      # still listed, but sale is stopped


def test_tour_page(client, db, catalog):
    tour = catalog["antalya"]
    tour.child_price = Decimal("400")
    tour.description = "Все включено"
    tour.flight_out, tour.flight_back = "PS 101", "PS 102"
    tour.program_days = [TourProgramDay(day_number=2, description="Екскурсія"),
                         TourProgramDay(day_number=1, description="Приліт")]
    tour.images = [TourImage(file_path="tours/x/b.png", sort_order=1),
                   TourImage(file_path="tours/x/a.jpg", sort_order=0)]
    tour.hotel.description = "Готель на першій лінії"
    db.flush()
    db.expire_all()

    response = client.get(f"{URL}/{tour.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["price_from_uah"] == "38400.00"
    assert body["child_price"] == "400.00" and body["child_price_uah"] == "19200.00"
    assert body["description"] == "Все включено"
    assert body["hotel_description"] == "Готель на першій лінії"
    assert (body["flight_out"], body["flight_back"]) == ("PS 101", "PS 102")
    assert [d["day_number"] for d in body["program_days"]] == [1, 2]
    assert [i["url"] for i in body["images"]] == ["/uploads/tours/x/a.jpg", "/uploads/tours/x/b.png"]
    assert body["image_url"] == "/uploads/tours/x/a.jpg"


def test_child_price_defaults_to_adult_price(client, catalog):
    body = client.get(f"{URL}/{catalog['hurghada'].id}").json()
    assert body["child_price"] is None
    assert body["child_price_uah"] == body["price_from_uah"] == "37800.00"


def test_hidden_tours_have_no_public_page(client, db, manager, catalog):
    for status, start in [(TourStatus.DRAFT, 30), (TourStatus.ARCHIVED, 30), (TourStatus.ACTIVE, -30)]:
        tour = make_active_tour(db, manager, days_ahead=start, status=status)
        response = client.get(f"{URL}/{tour.id}")
        assert response.status_code == 404, status
        assert response.json()["detail"] == "Тур не знайдено"
    assert client.get(f"{URL}/999999").status_code == 404


def test_published_tour_appears_in_catalog(client, db, manager, manager_headers):
    start = TODAY + timedelta(days=5)
    tour = make_tour(db, manager, title_en="Fresh", departure_from=start,
                     departure_to=start + timedelta(days=3))
    assert titles(client) == []
    client.post(f"/api/manager/tours/{tour.id}/publish", headers=manager_headers)
    assert titles(client) == ["Fresh"]
    client.post(f"/api/manager/tours/{tour.id}/unpublish", headers=manager_headers)
    assert titles(client) == []
