"""Administrator: reference data — CRUD, archive instead of delete, single default service."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Country, Hotel, InsuranceType, Language, TransferType
from app.models.enums import UserRole
from app.services import clock
from tests.factories import (country, headers_for, make_active_tour, make_hotel, make_order, make_user,
                             resort)

URL = "/api/admin"


@pytest.fixture()
def admin_headers(db):
    return headers_for(make_user(db, role=UserRole.ADMIN))


def post(client, headers, kind, body):
    return client.post(f"{URL}/{kind}", json=body, headers=headers)


def tour_payload(hotel_id, **extra):
    start = clock.today() + timedelta(days=30)
    return {"title_uk": "Тур", "title_en": "Tour", "hotel_id": hotel_id, "transport_type": "none",
            "departure_from": start.isoformat(), "departure_to": (start + timedelta(days=10)).isoformat(),
            "nights": 7, "seats_total": 10, "base_price": "800.00", "currency": "EUR",
            "program_days": [{"day_number": 1, "description": "Заселення"}]} | extra


# ---------- create / edit / delete
def test_country_resort_hotel_city_crud(client, db, admin_headers):
    created = post(client, admin_headers, "countries", {"iso_code": "is", "name_uk": "Ісландія"})
    assert created.status_code == 201, created.text
    croatia = created.json()
    assert (croatia["iso_code"], croatia["is_archived"]) == ("IS", False)
    assert post(client, admin_headers, "countries", {"iso_code": "IS", "name_uk": "Ще раз"}).status_code == 409
    assert post(client, admin_headers, "countries", {"iso_code": "HRV", "name_uk": "x"}).status_code == 422

    split = post(client, admin_headers, "resorts", {"country_id": croatia["id"], "name_uk": "Спліт"}).json()
    hotel = post(client, admin_headers, "hotels", {"resort_id": split["id"], "name": "Adriatic", "stars": 4})
    assert hotel.status_code == 201 and hotel.json()["rating_avg"] is None
    assert post(client, admin_headers, "hotels", {"resort_id": split["id"], "name": "X", "stars": 6}).status_code == 422
    city = post(client, admin_headers, "cities", {"country_id": croatia["id"], "name_uk": "Загреб",
                                                   "iata_code": "zag"})
    assert city.status_code == 201 and city.json()["iata_code"] == "ZAG"
    assert post(client, admin_headers, "cities", {"country_id": croatia["id"], "name_uk": "x",
                                                   "iata_code": "ZA"}).status_code == 422
    assert post(client, admin_headers, "resorts", {"country_id": 999999, "name_uk": "x"}).status_code == 422

    edited = client.patch(f"{URL}/hotels/{hotel.json()['id']}", json={"name": "Adriatic Palace", "stars": 5},
                          headers=admin_headers)
    assert edited.status_code == 200 and (edited.json()["name"], edited.json()["stars"]) == ("Adriatic Palace", 5)
    listed = client.get(f"{URL}/resorts", params={"parent_id": croatia["id"]}, headers=admin_headers).json()
    assert [r["name_uk"] for r in listed] == ["Спліт"]

    # Nothing refers to the city -> it can be deleted.
    assert client.delete(f"{URL}/cities/{city.json()['id']}", headers=admin_headers).status_code == 204
    assert client.delete(f"{URL}/cities/{city.json()['id']}", headers=admin_headers).status_code == 404


def test_hotel_rating_is_read_only(client, db, admin_headers):
    hotel = make_hotel(db, rating=4.5)
    response = client.patch(f"{URL}/hotels/{hotel.id}", json={"rating_avg": "5.00"}, headers=admin_headers)
    assert response.status_code == 422
    db.refresh(hotel)
    assert hotel.rating_avg == Decimal("4.50")


# ---------- archive instead of delete
def test_referenced_item_is_archived_not_deleted(client, db, customer, manager, manager_headers, admin_headers):
    tour = make_active_tour(db, manager)
    refused = client.delete(f"{URL}/hotels/{tour.hotel_id}", headers=admin_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Готель використовується (тури: 1) — архівуйте замість видалення"

    # A published tour uses the hotel: archiving is refused until the tour leaves the catalog.
    published = client.post(f"{URL}/hotels/{tour.hotel_id}/archive", headers=admin_headers)
    assert published.status_code == 409
    assert published.json()["detail"] == "Використовується в 1 опублікованому турі — спершу зніміть його з продажу"
    assert client.post(f"/api/manager/tours/{tour.id}/unpublish", headers=manager_headers).status_code == 200

    archived = client.post(f"{URL}/hotels/{tour.hotel_id}/archive", headers=admin_headers)
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    # Hidden from public lists and from new tours ...
    assert tour.hotel_id not in [h["id"] for h in client.get("/api/reference/hotels").json()]
    new_tour = client.post("/api/manager/tours", json=tour_payload(tour.hotel_id), headers=manager_headers)
    assert new_tour.status_code == 422
    # ... but the existing tour keeps it.
    assert client.get(f"/api/manager/tours/{tour.id}", headers=manager_headers).json()["hotel_id"] == tour.hotel_id

    restored = client.post(f"{URL}/hotels/{tour.hotel_id}/restore", headers=admin_headers)
    assert restored.json()["is_archived"] is False
    assert client.post("/api/manager/tours", json=tour_payload(tour.hotel_id),
                       headers=manager_headers).status_code == 201
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity == "hotel",
                                                       AuditLog.entity_id == str(tour.hotel_id))).all()
    assert actions == ["archived", "restored"]


def test_archived_country_hides_its_children(client, db, admin_headers):
    turkey = country(db, "TR")
    antalya = resort(db, "Antalya")
    hotel = make_hotel(db, resort_en="Antalya")
    assert antalya.id in [r["id"] for r in client.get("/api/reference/resorts").json()]
    assert client.post(f"{URL}/countries/{turkey.id}/archive", headers=admin_headers).status_code == 200
    assert turkey.id not in [c["id"] for c in client.get("/api/reference/countries").json()]
    assert antalya.id not in [r["id"] for r in client.get("/api/reference/resorts").json()]
    assert hotel.id not in [h["id"] for h in client.get("/api/reference/hotels").json()]
    assert all(c["country_id"] != turkey.id for c in client.get("/api/reference/cities").json())
    # A resort cannot be restored or created under an archived country.
    antalya.is_archived = True
    db.flush()
    assert client.post(f"{URL}/resorts/{antalya.id}/restore", headers=admin_headers).status_code == 409
    assert post(client, admin_headers, "resorts", {"country_id": turkey.id, "name_uk": "Кемер"}).status_code == 409


def test_archived_service_not_offered_for_new_orders(client, db, customer, customer_headers, manager,
                                                    admin_headers):
    extended = db.scalar(select(InsuranceType).where(InsuranceType.name_uk == "Розширене"))
    tour = make_active_tour(db, manager, days_ahead=10)
    old_order = make_order(db, customer, tour, insurance_type_id=extended.id)
    refused = client.delete(f"{URL}/insurance-types/{extended.id}", headers=admin_headers)
    assert refused.status_code == 409 and "замовлення: 1" in refused.json()["detail"]
    assert client.post(f"{URL}/insurance-types/{extended.id}/archive", headers=admin_headers).status_code == 200
    assert extended.id not in [i["id"] for i in client.get("/api/reference/insurance-types").json()]
    body = {"tour_id": tour.id, "start_date": tour.departure_from.isoformat(), "adults": 1,
            "insurance_type_id": extended.id}
    assert client.post("/api/orders", json=body, headers=customer_headers).status_code == 422
    db.refresh(old_order)
    assert old_order.insurance_type_id == extended.id                # existing order keeps it


# ---------- exactly one default
@pytest.mark.parametrize("kind, model", [("insurance-types", InsuranceType), ("transfer-types", TransferType)])
def test_single_default(client, db, admin_headers, kind, model):
    old_default = db.scalar(select(model).where(model.is_default.is_(True)))
    new = post(client, admin_headers, kind, {"name_uk": "Новий", "price_uah": "100", "is_default": True})
    assert new.status_code == 201 and new.json()["is_default"] is True
    db.expire_all()
    assert db.scalars(select(model.id).where(model.is_default.is_(True))).all() == [new.json()["id"]]
    assert db.get(model, old_default.id).is_default is False

    undefault = client.patch(f"{URL}/{kind}/{new.json()['id']}", json={"is_default": False}, headers=admin_headers)
    assert undefault.status_code == 409 and "призначте типовим інший" in undefault.json()["detail"]
    assert client.post(f"{URL}/{kind}/{new.json()['id']}/archive", headers=admin_headers).status_code == 409
    assert client.delete(f"{URL}/{kind}/{new.json()['id']}", headers=admin_headers).status_code == 409

    back = client.patch(f"{URL}/{kind}/{old_default.id}", json={"is_default": True}, headers=admin_headers)
    assert back.status_code == 200 and back.json()["is_default"] is True
    db.expire_all()
    assert db.scalars(select(model.id).where(model.is_default.is_(True))).all() == [old_default.id]
    assert client.delete(f"{URL}/{kind}/{new.json()['id']}", headers=admin_headers).status_code == 204
    assert post(client, admin_headers, kind, {"name_uk": "x", "price_uah": "-1"}).status_code == 422


# ---------- languages
def test_languages(client, db, admin_headers):
    created = client.post(f"{URL}/languages", json={"code": "PL", "name": "Polski", "is_enabled": False},
                          headers=admin_headers)
    assert created.status_code == 201 and created.json()["code"] == "pl"
    assert client.post(f"{URL}/languages", json={"code": "pl", "name": "x"}, headers=admin_headers).status_code == 409
    assert client.patch(f"{URL}/languages/en", json={"is_enabled": True}, headers=admin_headers).json()["is_enabled"]
    base = client.patch(f"{URL}/languages/uk", json={"is_enabled": False}, headers=admin_headers)
    assert base.status_code == 409 and "основна мова" in base.json()["detail"]
    assert client.delete(f"{URL}/languages/uk", headers=admin_headers).status_code == 409
    assert client.delete(f"{URL}/languages/pl", headers=admin_headers).status_code == 204
    assert db.get(Language, "pl") is None


# ---------- audit and access
def test_changes_are_audited(client, db, admin_headers):
    item = post(client, admin_headers, "countries", {"iso_code": "NO", "name_uk": "Норвегія"}).json()
    client.patch(f"{URL}/countries/{item['id']}", json={"name_en": "Norway"}, headers=admin_headers)
    client.delete(f"{URL}/countries/{item['id']}", headers=admin_headers)
    rows = db.scalars(select(AuditLog).where(AuditLog.entity == "country", AuditLog.entity_id == str(item["id"]))
                      .order_by(AuditLog.id)).all()
    assert [r.action for r in rows] == ["created", "updated", "deleted"]
    assert (rows[1].old_value, rows[1].new_value) == ({"name_en": None}, {"name_en": "Norway"})
    assert rows[2].old_value["iso_code"] == "NO"


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.FINANCE])
def test_reference_admin_only_for_admins(client, db, role):
    headers = headers_for(make_user(db, role=role))
    first_country = db.scalar(select(Country.id))
    for call in (lambda h: client.get(f"{URL}/countries", headers=h),
                 lambda h: client.post(f"{URL}/countries", json={"iso_code": "XX", "name_uk": "x"}, headers=h),
                 lambda h: client.patch(f"{URL}/countries/{first_country}", json={"name_uk": "x"}, headers=h),
                 lambda h: client.post(f"{URL}/countries/{first_country}/archive", headers=h),
                 lambda h: client.delete(f"{URL}/countries/{first_country}", headers=h),
                 lambda h: client.get(f"{URL}/languages", headers=h)):
        assert call(headers).status_code == 403
        assert call({}).status_code == 401
    assert db.get(Country, first_country).is_archived is False
    assert Hotel and TransferType
