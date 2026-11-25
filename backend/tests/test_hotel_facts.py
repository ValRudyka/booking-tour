"""Structured hotel facts: the admin's hotel reference (form 4.6.4.2) and the tour page."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, Hotel
from app.models.enums import UserRole
from tests.factories import headers_for, make_active_tour, make_hotel, make_user, resort

URL = "/api/admin/hotels"
FACTS = {"beach_line": 1, "distance_to_beach_m": 0, "distance_to_airport_km": 12,
         "check_in": "14:00", "check_out": "12:00",
         "amenities": [" Власний пляж ", "SPA-центр", "", "Власний пляж"],
         "room_types": ["Стандартний номер", "Сімейний номер"]}


@pytest.fixture()
def admin_headers(db):
    return headers_for(make_user(db, role=UserRole.ADMIN))


@pytest.fixture()
def hurghada(db):
    return resort(db, "Hurghada")


def test_admin_creates_a_hotel_with_facts_and_audit(client, db, admin_headers, hurghada):
    response = client.post(URL, headers=admin_headers,
                           json={"resort_id": hurghada.id, "name": "Coral Bay", **FACTS})
    assert response.status_code == 201, response.text
    hotel = response.json()
    assert hotel["check_in"] == "14:00:00" and hotel["check_out"] == "12:00:00"
    assert hotel["amenities"] == ["Власний пляж", "SPA-центр"]       # trimmed, no empty or repeated
    assert (hotel["beach_line"], hotel["distance_to_beach_m"], hotel["distance_to_airport_km"]) == (1, 0, 12)

    entry = db.scalar(select(AuditLog).where(AuditLog.entity == "hotel", AuditLog.action == "created",
                                             AuditLog.entity_id == str(hotel["id"])))
    assert entry.new_value["check_in"] == "14:00:00"
    assert entry.new_value["room_types"] == ["Стандартний номер", "Сімейний номер"]


def test_admin_patches_facts_and_the_audit_keeps_old_values(client, db, admin_headers, hurghada):
    hotel = client.post(URL, headers=admin_headers,
                        json={"resort_id": hurghada.id, "name": "Coral Bay", **FACTS}).json()
    patched = client.patch(f"{URL}/{hotel['id']}", headers=admin_headers,
                           json={"distance_to_airport_km": 15, "amenities": ["Аквапарк"]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["amenities"] == ["Аквапарк"]
    assert patched.json()["room_types"] == FACTS["room_types"]      # not sent, not changed
    entry = db.scalars(select(AuditLog).where(AuditLog.entity == "hotel", AuditLog.action == "updated")
                       .order_by(AuditLog.id.desc())).first()
    assert entry.old_value == {"distance_to_airport_km": 12, "amenities": ["Власний пляж", "SPA-центр"]}
    assert entry.new_value == {"distance_to_airport_km": 15, "amenities": ["Аквапарк"]}


def test_facts_are_optional(client, admin_headers, hurghada):
    hotel = client.post(URL, headers=admin_headers, json={"resort_id": hurghada.id, "name": "Plain"}).json()
    assert (hotel["beach_line"], hotel["check_in"], hotel["amenities"]) == (None, None, [])


@pytest.mark.parametrize("field, value, message", [
    ("beach_line", 0, "«Лінія пляжу» — від 1 до 5"),
    ("beach_line", 6, "«Лінія пляжу» — від 1 до 5"),
    ("distance_to_beach_m", -1, "«Відстань до пляжу, м» — від 0 до 50000"),
    ("distance_to_airport_km", 1001, "«Відстань до аеропорту, км» — від 0 до 1000"),
    ("amenities", ["x" * 201], "Зручності: кожен пункт — не довше 200 символів"),
    ("room_types", [f"Номер {n}" for n in range(21)], "Типи номерів: не більше 20 пунктів"),
])
def test_fact_limits(client, admin_headers, hurghada, field, value, message):
    response = client.post(URL, headers=admin_headers,
                           json={"resort_id": hurghada.id, "name": "X", field: value})
    assert response.status_code == 422 and response.json()["detail"] == message


def test_wrong_time_format_is_rejected(client, admin_headers, hurghada):
    response = client.post(URL, headers=admin_headers,
                           json={"resort_id": hurghada.id, "name": "X", "check_in": "2pm"})
    assert response.status_code == 422


def test_database_checks(db):
    hotel = make_hotel(db)
    for column, value in (("beach_line", 9), ("distance_to_beach_m", -5), ("distance_to_airport_km", -1)):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(Hotel.__table__.update().where(Hotel.id == hotel.id).values({column: value}))


def test_tour_page_shows_the_facts_and_the_card_does_not(client, db, manager):
    hotel = make_hotel(db, name="Coral Bay", beach_line=1, distance_to_beach_m=0, distance_to_airport_km=12,
                       amenities=["SPA-центр"], room_types=["Сімейний номер"])
    tour = make_active_tour(db, manager, hotel_id=hotel.id)
    page = client.get(f"/api/tours/{tour.id}").json()["hotel"]
    assert (page["beach_line"], page["distance_to_beach_m"], page["amenities"], page["room_types"]) == (
        1, 0, ["SPA-центр"], ["Сімейний номер"])
    card = client.get("/api/tours").json()["items"][0]["hotel"]
    assert "amenities" not in card and "beach_line" not in card
    reference = client.get("/api/reference/hotels").json()
    assert all("amenities" not in h for h in reference)
