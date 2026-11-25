"""Manager tour management: create, edit, copy, statuses (ТЗ 4.5.2, form 4.6.2.1, 4.4.1)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Hotel, Tour
from app.models.enums import TourStatus, UserRole
from app.services import clock
from tests.factories import copy_dates, error_text, city, headers_for, make_hotel, make_tour, make_user

URL = "/api/manager/tours"


def payload(hotel_id, **overrides):
    start = clock.today() + timedelta(days=30)
    data = {"title_uk": "Анталія, все включено", "title_en": "Antalya all inclusive",
            "hotel_id": hotel_id, "transport_type": "none", "departure_from": start.isoformat(),
            "departure_to": (start + timedelta(days=20)).isoformat(), "nights": 7,
            "seats_total": 20, "base_price": "850.00", "currency": "EUR",
            "program_days": [{"day_number": 1, "description": "Заселення"},
                             {"day_number": 2, "description": "Екскурсія"}]}
    data.update(overrides)
    return data


@pytest.fixture()
def hotel(db):
    return make_hotel(db, name="Rixos", resort_en="Antalya", stars=5)


def create(client, headers, hotel, **overrides):
    response = client.post(URL, json=payload(hotel.id, **overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------- access
@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.FINANCE, UserRole.ADMIN])
def test_only_manager_has_access(client, db, hotel, role):
    headers = headers_for(make_user(db, role=role))
    tour = make_tour(db, make_user(db, role=UserRole.MANAGER))
    requests = [("get", URL), ("post", URL), ("get", f"{URL}/{tour.id}"),
                ("patch", f"{URL}/{tour.id}"), ("post", f"{URL}/{tour.id}/copy"),
                ("post", f"{URL}/{tour.id}/publish"), ("post", f"{URL}/{tour.id}/unpublish"),
                ("post", f"{URL}/{tour.id}/archive"), ("post", f"{URL}/{tour.id}/images"),
                ("delete", f"{URL}/{tour.id}/images/1"), ("put", f"{URL}/{tour.id}/images/order")]
    for method, url in requests:
        assert client.request(method, url, headers=headers).status_code == 403, (method, url)
        assert client.request(method, url).status_code == 401, (method, url)


# ---------- create
def test_create_tour_as_draft(client, db, manager, manager_headers, hotel):
    body = create(client, manager_headers, hotel)
    assert body["status"] == "draft"
    assert body["created_by"] == manager.id
    assert body["seats_sold"] == 0
    assert [d["day_number"] for d in body["program_days"]] == [1, 2]
    assert db.get(Tour, body["id"]).status == TourStatus.DRAFT


def test_ukrainian_title_generated_from_hotel_and_resort(client, manager_headers, hotel):
    body = create(client, manager_headers, hotel, title_uk="  ")
    assert body["title_uk"] == "Rixos, Анталія"


def test_flight_numbers_normalized_for_air(client, db, manager_headers, hotel):
    body = create(client, manager_headers, hotel, transport_type="air",
                  departure_city_id=city(db, "Warsaw").id, flight_out="qu  4433", flight_back="PS101")
    assert (body["flight_out"], body["flight_back"]) == ("QU 4433", "PS101")


@pytest.mark.parametrize("overrides,message", [
    ({"nights": 0}, "від 1 до 30 ночей"),
    ({"nights": 31}, "від 1 до 30 ночей"),
    ({"departure_to": (clock.today() + timedelta(days=1)).isoformat()}, "не може бути раніше"),
    ({"base_price": "0"}, "більшою за 0"),
    ({"child_price": "-1"}, "від'ємною"),
    ({"seats_total": 0}, "не менше 1"),
    ({"title_en": " "}, "англійською"),
    ({"title_uk": "Т" * 201}, "200 символів"),
    ({"description": "x" * 5001}, "5000 символів"),
    ({"transport_type": "air"}, "місто відправлення"),
    ({"transport_type": "bus"}, "місто відправлення"),
    ({"flight_out": "QU 4433"}, "лише для авіаперельоту"),
    ({"program_days": [{"day_number": 1, "description": "a"}, {"day_number": 3, "description": "b"}]},
     "по порядку"),
    ({"program_days": [{"day_number": 1, "description": "a"}, {"day_number": 1, "description": "b"}]},
     "по порядку"),
    ({"program_days": [{"day_number": 1, "description": " "}]}, "кожного дня"),
    ({"nights": 1, "program_days": [{"day_number": n, "description": "x"} for n in (1, 2, 3)]},
     "максимум 2"),
])
def test_create_validation(client, manager_headers, hotel, overrides, message):
    response = client.post(URL, json=payload(hotel.id, **overrides), headers=manager_headers)
    assert response.status_code == 422, response.text
    assert message in error_text(response)


def test_wrong_flight_format(client, db, manager_headers, hotel):
    response = client.post(URL, json=payload(hotel.id, transport_type="air",
                                             departure_city_id=city(db, "Warsaw").id,
                                             flight_out="рейс 1"), headers=manager_headers)
    assert response.status_code == 422
    assert "QU 4433" in error_text(response)


def test_unknown_or_archived_hotel_and_city(client, db, manager_headers, hotel):
    archived = make_hotel(db, name="Old", is_archived=True)
    for hotel_id in (999999, archived.id):
        response = client.post(URL, json=payload(hotel_id), headers=manager_headers)
        assert response.status_code == 422, hotel_id
    kyiv = city(db, "Kyiv")
    kyiv.is_archived = True
    db.flush()
    response = client.post(URL, json=payload(hotel.id, transport_type="bus", departure_city_id=kyiv.id),
                           headers=manager_headers)
    assert response.status_code == 422
    assert error_text(response) == "Місто відправлення або його країна в архіві — оберіть інше місто"


# ---------- edit
def test_update_draft(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel)
    response = client.patch(f"{URL}/{tour['id']}", json={"nights": 10, "base_price": "999.50"},
                            headers=manager_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["nights"], body["base_price"]) == (10, "999.50")
    assert body["title_en"] == "Antalya all inclusive"  # untouched fields stay


def test_update_checks_merged_tour(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel)  # program of 2 days
    response = client.patch(f"{URL}/{tour['id']}", json={"nights": 0}, headers=manager_headers)
    assert response.status_code == 422
    # the dates are validated together with the stored "from" date
    response = client.patch(f"{URL}/{tour['id']}",
                            json={"departure_to": clock.today().isoformat()}, headers=manager_headers)
    assert response.status_code == 422


def test_update_program_replaces_whole_list(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel)
    response = client.patch(f"{URL}/{tour['id']}",
                            json={"program_days": [{"day_number": 1, "description": "Новий день"}]},
                            headers=manager_headers)
    assert response.status_code == 200
    assert response.json()["program_days"] == [{"day_number": 1, "description": "Новий день"}]


def test_update_cannot_lower_quota_below_sold(client, db, manager_headers, hotel):
    tour = create(client, manager_headers, hotel)
    db.get(Tour, tour["id"]).seats_sold = 5
    db.flush()
    response = client.patch(f"{URL}/{tour['id']}", json={"seats_total": 4}, headers=manager_headers)
    assert response.status_code == 422
    assert "(5)" in error_text(response)


@pytest.mark.parametrize("tour_status", [TourStatus.ACTIVE, TourStatus.ARCHIVED])
def test_only_draft_can_be_edited(client, db, manager, manager_headers, tour_status):
    tour = make_tour(db, manager, status=tour_status)
    response = client.patch(f"{URL}/{tour.id}", json={"nights": 5}, headers=manager_headers)
    assert response.status_code == 409


def test_unknown_tour_is_404(client, manager_headers):
    assert client.get(f"{URL}/999999", headers=manager_headers).status_code == 404
    assert client.patch(f"{URL}/999999", json={}, headers=manager_headers).status_code == 404
    assert client.post(f"{URL}/999999/publish", headers=manager_headers).status_code == 404


# ---------- statuses
def audit_rows(db, tour_id):
    return db.scalars(select(AuditLog).where(AuditLog.entity == "tour",
                                             AuditLog.entity_id == str(tour_id))
                      .order_by(AuditLog.id)).all()


def test_publish_unpublish_archive_with_audit(client, db, manager, manager_headers, hotel):
    tour_id = create(client, manager_headers, hotel)["id"]
    for action, expected in [("publish", "active"), ("unpublish", "draft"), ("publish", "active"),
                             ("archive", "archived")]:
        response = client.post(f"{URL}/{tour_id}/{action}", headers=manager_headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected
    rows = audit_rows(db, tour_id)
    assert [(r.old_value["status"], r.new_value["status"]) for r in rows] == [
        ("draft", "active"), ("active", "draft"), ("draft", "active"), ("active", "archived")]
    assert all(r.user_id == manager.id and r.action == "status_change" for r in rows)


def test_draft_can_be_archived(client, db, manager, manager_headers):
    tour = make_tour(db, manager)
    assert client.post(f"{URL}/{tour.id}/archive", headers=manager_headers).json()["status"] == "archived"


@pytest.mark.parametrize("start,action", [
    (TourStatus.ARCHIVED, "publish"), (TourStatus.ARCHIVED, "unpublish"),
    (TourStatus.ARCHIVED, "archive"), (TourStatus.ACTIVE, "publish"), (TourStatus.DRAFT, "unpublish"),
])
def test_forbidden_transitions(client, db, manager, manager_headers, start, action):
    tour = make_tour(db, manager, status=start)
    response = client.post(f"{URL}/{tour.id}/{action}", headers=manager_headers)
    assert response.status_code == 409
    assert "Неможливо змінити статус" in error_text(response)
    assert audit_rows(db, tour.id) == []


def test_publish_rejects_past_dates(client, db, manager, manager_headers):
    tour = make_tour(db, manager, departure_from=clock.today() - timedelta(days=20),
                     departure_to=clock.today() - timedelta(days=1))
    response = client.post(f"{URL}/{tour.id}/publish", headers=manager_headers)
    assert response.status_code == 422
    assert "минули" in error_text(response)


def test_publish_rejects_archived_hotel(client, db, manager, manager_headers):
    tour = make_active_ready_tour(db, manager)
    db.get(Hotel, tour.hotel_id).is_archived = True
    db.flush()
    response = client.post(f"{URL}/{tour.id}/publish", headers=manager_headers)
    assert response.status_code == 422
    assert db.get(Tour, tour.id).status == TourStatus.DRAFT


def make_active_ready_tour(db, manager):
    start = clock.today() + timedelta(days=10)
    return make_tour(db, manager, departure_from=start, departure_to=start + timedelta(days=5))


# ---------- copy
def test_copy_creates_new_draft_with_new_dates(client, db, manager, manager_headers, hotel):
    source = create(client, manager_headers, hotel, is_featured=True)
    client.post(f"{URL}/{source['id']}/publish", headers=manager_headers)
    db.get(Tour, source["id"]).seats_sold = 3
    db.flush()
    other_manager = make_user(db, role=UserRole.MANAGER)
    dates = copy_dates(days_ahead=90)
    response = client.post(f"{URL}/{source['id']}/copy", json=dates, headers=headers_for(other_manager))
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != source["id"]
    assert copy["status"] == "draft"
    assert copy["seats_sold"] == 0
    assert copy["created_by"] == other_manager.id
    assert copy["title_uk"] == "Копія — Анталія, все включено"
    assert copy["title_en"] == "Copy — Antalya all inclusive"
    assert copy["program_days"] == source["program_days"]
    # the dates come from the dialog, never from the source
    assert (copy["departure_from"], copy["departure_to"]) == (dates["departure_from"], dates["departure_to"])
    assert copy["departure_from"] != source["departure_from"]
    assert copy["is_featured"] is False
    assert (copy["base_price"], copy["seats_total"]) == (source["base_price"], source["seats_total"])
    assert db.get(Tour, source["id"]).status == TourStatus.ACTIVE  # source untouched


def test_copy_title_is_cut_to_the_limit(client, db, manager, manager_headers):
    tour = make_tour(db, manager, title_uk="Т" * 200, title_en="T" * 200)
    copy = client.post(f"{URL}/{tour.id}/copy", json=copy_dates(), headers=manager_headers).json()
    assert len(copy["title_uk"]) == len(copy["title_en"]) == 200
    assert copy["title_uk"].startswith("Копія — ")


@pytest.mark.parametrize("body,field", [
    ({"departure_from": 0, "departure_to": 5}, "departure_from"),   # today: not bookable
    ({"departure_from": 10, "departure_to": 5}, "departure_to"),
])
def test_copy_checks_new_dates(client, db, manager, manager_headers, body, field):
    tour = make_tour(db, manager)
    dates = {key: (clock.today() + timedelta(days=value)).isoformat() for key, value in body.items()}
    response = client.post(f"{URL}/{tour.id}/copy", json=dates, headers=manager_headers)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert client.post(f"{URL}/{tour.id}/copy", headers=manager_headers).status_code == 422  # no body


def test_archived_tour_can_be_copied(client, db, manager, manager_headers):
    tour = make_tour(db, manager, status=TourStatus.ARCHIVED)
    response = client.post(f"{URL}/{tour.id}/copy", json=copy_dates(), headers=manager_headers)
    assert response.status_code == 201


# ---------- list
def test_manager_list_filters_and_pages(client, db, manager, manager_headers):
    for i in range(3):
        make_tour(db, manager, title_uk=f"Чернетка {i}", title_en=f"Draft {i}")
    make_tour(db, manager, title_uk="Активний тур", status=TourStatus.ACTIVE)
    make_tour(db, manager, title_uk="Старий", status=TourStatus.ARCHIVED)

    body = client.get(URL, params={"status": "draft", "page_size": 2}, headers=manager_headers).json()
    assert (body["total"], len(body["items"])) == (3, 2)
    assert {item["status"] for item in body["items"]} == {"draft"}
    body = client.get(URL, params={"status": "draft", "page_size": 2, "page": 2},
                      headers=manager_headers).json()
    assert len(body["items"]) == 1
    body = client.get(URL, params={"q": "актив"}, headers=manager_headers).json()
    assert [item["title_uk"] for item in body["items"]] == ["Активний тур"]
    assert client.get(URL, headers=manager_headers).json()["total"] == 5
