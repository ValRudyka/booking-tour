"""Spec 13: the admin pages show the safety rules before a request (user_actions, admin_actions),
archiving and publishing with archived reference records, and the temporary staff password."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, City, Country, Hotel, Resort, Tour, User
from app.models.enums import TourStatus, UserRole
from app.services import clock
from tests.factories import city, country, headers_for, make_active_tour, make_hotel, make_order, make_tour, make_user

URL = "/api/admin"


@pytest.fixture()
def admin(db):
    # Other admins of the database must not make "the last admin" rule depend on the data.
    for other in db.scalars(select(User).where(User.role == UserRole.ADMIN)):
        other.is_active = False
    db.flush()
    return make_user(db, role=UserRole.ADMIN)


@pytest.fixture()
def admin_headers(admin):
    return headers_for(admin)


def actions_of(body: dict, key="user_actions") -> dict:
    return {a["action"]: (a["allowed"], a["reason"]) for a in body[key]}


# ---------- users
def test_user_actions_show_the_safety_rules(client, db, admin, admin_headers):
    me = actions_of(client.get(f"{URL}/users/{admin.id}", headers=admin_headers).json())
    assert me["block"] == (False, "Не можна заблокувати себе")
    assert me["change_role"] == (False, "Не можна змінити власну роль")
    assert me["reset_password"][0] is False and "Змінити пароль" in me["reset_password"][1]
    assert me["edit"] == (True, None)

    customer = make_user(db)
    theirs = actions_of(client.get(f"{URL}/users/{customer.id}", headers=admin_headers).json())
    assert theirs["edit"][0] is False and "у профілі" in theirs["edit"][1]
    assert theirs["change_role"][0] is False and "Роль клієнта" in theirs["change_role"][1]
    assert theirs["block"] == (True, None) and theirs["reset_password"] == (True, None)

    # The last active admin, seen by another (blocked) admin's list: block/role refused.
    other_admin = make_user(db, role=UserRole.ADMIN)
    other = actions_of(client.get(f"{URL}/users/{other_admin.id}", headers=admin_headers).json())
    assert other["block"] == (True, None)                       # two active admins now
    other_admin.is_active = False
    db.flush()
    other = actions_of(client.get(f"{URL}/users/{other_admin.id}", headers=admin_headers).json())
    assert "unblock" in other and "block" not in other


def test_last_admin_reason_matches_the_endpoint(client, db, admin):
    second = make_user(db, role=UserRole.ADMIN)
    headers = headers_for(second)
    assert client.patch(f"{URL}/users/{second.id}", json={"is_active": False}, headers=headers).status_code == 409
    second_view = actions_of(client.get(f"{URL}/users/{admin.id}", headers=headers).json())
    assert second_view["block"] == (True, None)
    assert client.patch(f"{URL}/users/{admin.id}", json={"is_active": False}, headers=headers).status_code == 200
    # Now `second` is the last active admin; a list read by the blocked admin's token is refused,
    # so check the rule through the service functions the list uses.
    from app.services import admin_users

    ids = admin_users.active_admin_ids(db)
    assert admin_users.block_refusal(admin, second, ids) == admin_users.LAST_ADMIN
    assert admin_users.role_refusal(admin, second, ids) == admin_users.LAST_ADMIN


def test_client_data_is_not_edited_but_client_can_be_blocked(client, db, admin_headers):
    customer = make_user(db)
    refused = client.patch(f"{URL}/users/{customer.id}", json={"last_name": "Інше"}, headers=admin_headers)
    assert refused.status_code == 409 and "у профілі" in refused.json()["detail"]
    assert client.patch(f"{URL}/users/{customer.id}", json={"is_active": False},
                        headers=admin_headers).status_code == 200


def test_admin_cannot_reset_own_password_here(client, db, admin, admin_headers):
    response = client.post(f"{URL}/users/{admin.id}/reset-password", json={"new_password": "Another-pass-1"},
                           headers=admin_headers)
    assert response.status_code == 409 and "Змінити пароль" in response.json()["detail"]


def test_staff_filter(client, db, admin_headers):
    make_user(db, role=UserRole.FINANCE)
    make_user(db)
    staff = client.get(f"{URL}/users", params={"staff": "true", "page_size": 100}, headers=admin_headers).json()
    clients = client.get(f"{URL}/users", params={"staff": "false", "page_size": 100}, headers=admin_headers).json()
    assert staff["items"] and {u["role"] for u in staff["items"]} <= {"manager", "finance", "admin"}
    assert clients["items"] and {u["role"] for u in clients["items"]} == {"client"}


def test_temporary_password_is_shown_once_and_never_logged(client, db, admin_headers):
    body = {"role": "manager", "phone": "+380671115544", "email": "temp.staff@tour.ua",
            "last_name": "Коваль", "first_name": "Олена"}
    response = client.post(f"{URL}/users", json=body, headers=admin_headers)
    assert response.status_code == 201, response.text
    created = response.json()
    password = created["temporary_password"]
    assert len(password) == 16 and any(c.isdigit() for c in password) and any(c.isupper() for c in password)
    login = client.post("/api/auth/login", data={"username": "+380671115544", "password": password})
    assert login.status_code == 200
    # Not in the user's other answers ...
    assert "temporary_password" not in client.get(f"{URL}/users/{created['id']}", headers=admin_headers).json()
    # ... and not in the audit log (any row, any field).
    rows = db.scalars(select(AuditLog).where(AuditLog.entity == "user", AuditLog.entity_id == str(created["id"]))).all()
    assert [r.action for r in rows] == ["created"]
    text = " ".join(str(r.old_value) + str(r.new_value) for r in rows)
    assert password not in text and "password" not in text and "$argon2" not in text
    # A password chosen by the caller (CLI, tests) is never echoed.
    chosen = client.post(f"{URL}/users", json={**body, "phone": "+380671115545", "email": "chosen@tour.ua",
                                               "password": "Chosen-pass-1"}, headers=admin_headers)
    assert chosen.status_code == 201 and chosen.json()["temporary_password"] is None


# ---------- reference records
def test_archive_refused_while_published_tours_use_the_record(client, db, manager, admin_headers):
    hotel = make_hotel(db, name="Busy", resort_en="Kemer")
    kyiv = city(db, "Kyiv")
    tour = make_active_tour(db, manager, hotel_id=hotel.id, departure_city_id=kyiv.id)
    make_tour(db, manager, hotel_id=hotel.id)                   # a draft does not count
    resort_id, country_id = hotel.resort_id, db.get(Resort, hotel.resort_id).country_id
    for kind, item_id in (("hotels", hotel.id), ("resorts", resort_id), ("countries", country_id),
                          ("cities", kyiv.id)):
        refused = client.post(f"{URL}/{kind}/{item_id}/archive", headers=admin_headers)
        assert refused.status_code == 409, kind
        assert "опублікован" in refused.json()["detail"] and "зніміть" in refused.json()["detail"]
        listed = next(i for i in client.get(f"{URL}/{kind}", headers=admin_headers).json() if i["id"] == item_id)
        assert actions_of(listed, "admin_actions")["archive"] == (False, refused.json()["detail"])
    tour.status = TourStatus.DRAFT
    db.flush()
    assert client.post(f"{URL}/hotels/{hotel.id}/archive", headers=admin_headers).status_code == 200


def test_reference_actions_restore_default_delete(client, db, admin_headers):
    turkey = country(db, "TR")
    kemer = db.get(Resort, make_hotel(db, name="In Kemer", resort_en="Kemer").resort_id)
    new = client.post(f"{URL}/resorts", json={"country_id": turkey.id, "name_uk": "Белек"},
                      headers=admin_headers).json()
    assert actions_of(new, "admin_actions")["delete"] == (True, None)
    assert client.post(f"{URL}/resorts/{new['id']}/archive", headers=admin_headers).status_code == 200
    turkey.is_archived = True
    db.flush()
    listed = {i["id"]: i for i in client.get(f"{URL}/resorts", headers=admin_headers).json()}
    restore = actions_of(listed[new["id"]], "admin_actions")["restore"]
    assert restore[0] is False and "Країна архівна" in restore[1]
    assert client.post(f"{URL}/resorts/{new['id']}/restore", headers=admin_headers).json()["detail"] == restore[1]
    # A resort with hotels: delete refused in readable words.
    delete = actions_of(listed[kemer.id], "admin_actions")["delete"]
    assert delete[0] is False and "готелі:" in delete[1]
    # The default insurance cannot be archived or deleted; another one can become the default.
    insurance = client.get(f"{URL}/insurance-types", headers=admin_headers).json()
    default = next(i for i in insurance if i["is_default"])
    other = next(i for i in insurance if not i["is_default"] and not i["is_archived"])
    assert actions_of(default, "admin_actions")["archive"][0] is False
    assert "make_default" not in actions_of(default, "admin_actions")
    assert actions_of(other, "admin_actions")["make_default"] == (True, None)


def test_language_actions(client, admin_headers):
    languages = {lang["code"]: actions_of(lang, "admin_actions")
                 for lang in client.get(f"{URL}/languages", headers=admin_headers).json()}
    assert languages["uk"]["disable"][0] is False and languages["uk"]["delete"][0] is False


# ---------- publishing with archived records (services/tours.py: _validate_for_publish)
def draft_ready(db, manager, **overrides):
    start = clock.today() + timedelta(days=10)
    return make_tour(db, manager, departure_from=start, departure_to=start + timedelta(days=5), **overrides)


@pytest.mark.parametrize("archive", ["resort", "country", "city"])
def test_publish_refused_with_an_archived_record(client, db, manager, manager_headers, archive):
    hotel = make_hotel(db, name="Seaside", resort_en="Kemer")
    kyiv = city(db, "Kyiv")
    tour = draft_ready(db, manager, hotel_id=hotel.id, departure_city_id=kyiv.id)
    resort = db.get(Resort, hotel.resort_id)
    record = {"resort": resort, "country": db.get(Country, resort.country_id), "city": kyiv}[archive]
    record.is_archived = True
    db.flush()
    response = client.post(f"/api/manager/tours/{tour.id}/publish", headers=manager_headers)
    assert response.status_code == 422
    detail = str(response.json()["detail"])
    assert "в архіві" in detail
    assert db.get(Tour, tour.id).status == TourStatus.DRAFT


def test_old_orders_still_show_archived_records(client, db, manager, customer, admin_headers):
    """Criterion 8.3: an archived country leaves the catalog filters, old orders open normally."""
    hotel = make_hotel(db, name="Old trip", resort_en="Kemer")
    tour = make_tour(db, manager, hotel_id=hotel.id, departure_city_id=city(db, "Kyiv").id)
    order = make_order(db, customer, tour)
    turkey = db.get(Country, db.get(Resort, hotel.resort_id).country_id)
    assert client.post(f"{URL}/countries/{turkey.id}/archive", headers=admin_headers).status_code == 200
    assert turkey.id not in [c["id"] for c in client.get("/api/reference/countries").json()]
    page = client.get(f"/api/orders/{order.id}", headers=headers_for(customer))
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["country_name"] == turkey.name_uk and body["hotel_name"] == "Old trip"
    assert Hotel and City
