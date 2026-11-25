"""Saved passports for autofill (ТЗ form 4.6.1.1, field 8)."""
from datetime import timedelta

import pytest

from app.models.enums import UserRole
from app.services import clock
from tests.factories import headers_for, make_user

URL = "/api/me/passports"


def passport(**overrides):
    data = {"last_name_lat": "Shevchenko", "first_name_lat": "Taras",
            "passport_number": "fx 123456", "issuing_authority": "1234",
            "expiry_date": (clock.today() + timedelta(days=700)).isoformat(), "birth_date": "1988-03-09"}
    return data | overrides


def test_add_list_delete(client, customer_headers):
    response = client.post(URL, json=passport(), headers=customer_headers)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["passport_number"] == "FX123456"          # spaces removed, upper case
    assert saved["birth_date"] == "1988-03-09"
    client.post(URL, json=passport(first_name_lat="Olena", issuing_authority=None, passport_number="FX654321"),
                headers=customer_headers)
    names = [p["first_name_lat"] for p in client.get(URL, headers=customer_headers).json()]
    assert names == ["Taras", "Olena"]
    assert client.delete(f"{URL}/{saved['id']}", headers=customer_headers).status_code == 204
    assert [p["first_name_lat"] for p in client.get(URL, headers=customer_headers).json()] == ["Olena"]


@pytest.mark.parametrize("overrides,message", [
    ({"last_name_lat": "Шевченко"}, "латиницею"),
    ({"first_name_lat": "Taras2"}, "латиницею"),
    ({"passport_number": "FX-12"}, "4–20 символів"),
    ({"issuing_authority": "12a4"}, "4-значний"),
    ({"expiry_date": clock.today().isoformat()}, "пізнішим за сьогоднішню"),
    ({"birth_date": (clock.today() + timedelta(days=1)).isoformat()}, "не може бути пізнішою"),
    ({"birth_date": "1899-12-31"}, "Перевірте дату народження"),
])
def test_validation(client, customer_headers, overrides, message):
    """Every rule names its field (loc), so the form shows it under that field."""
    response = client.post(URL, json=passport(**overrides), headers=customer_headers)
    assert response.status_code == 422
    [issue] = response.json()["detail"]
    assert issue["loc"] == ["body", next(iter(overrides))] and issue["type"] == "profile_rule"
    assert message in issue["msg"]


def test_birth_date_is_required_for_new_passports(client, customer_headers):
    data = passport()
    del data["birth_date"]
    response = client.post(URL, json=data, headers=customer_headers)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "birth_date"]


def test_edit(client, customer_headers):
    saved = client.post(URL, json=passport(), headers=customer_headers).json()
    response = client.put(f"{URL}/{saved['id']}", headers=customer_headers, json=passport(
        first_name_lat="Taras  Hryhorovych", passport_number="FX 123456", issuing_authority="",
        birth_date="1988-03-10"))
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["id"] == saved["id"] and edited["first_name_lat"] == "Taras Hryhorovych"
    assert edited["issuing_authority"] is None and edited["birth_date"] == "1988-03-10"
    assert client.get(URL, headers=customer_headers).json() == [edited]
    refused = client.put(f"{URL}/{saved['id']}", headers=customer_headers, json=passport(last_name_lat="Шевченко"))
    assert refused.status_code == 422
    assert client.get(URL, headers=customer_headers).json() == [edited]   # nothing changed


def test_same_number_twice_is_refused(client, customer_headers):
    first = client.post(URL, json=passport(), headers=customer_headers).json()
    second = client.post(URL, json=passport(passport_number="FX999999"), headers=customer_headers).json()
    response = client.post(URL, json=passport(passport_number="fx123456"), headers=customer_headers)
    assert response.status_code == 409
    assert response.json()["detail"][0]["loc"] == ["body", "passport_number"]
    clash = client.put(f"{URL}/{second['id']}", headers=customer_headers, json=passport())
    assert clash.status_code == 409
    # Saving a passport with its own number is not a clash.
    assert client.put(f"{URL}/{first['id']}", headers=customer_headers, json=passport()).status_code == 200


def test_old_rows_without_birth_date(client, db, customer_headers):
    """Saved before the migration: listed with birth_date null (the checkout asks for it)."""
    from datetime import date

    from app.models import SavedPassport
    me = client.get("/api/auth/me", headers=customer_headers).json()
    db.add(SavedPassport(user_id=me["id"], last_name_lat="Old", first_name_lat="Row", passport_number="AA1111",
                         expiry_date=date(2099, 1, 1)))
    db.flush()
    assert client.get(URL, headers=customer_headers).json()[0]["birth_date"] is None


def test_only_own_passports(client, db, customer_headers):
    other = headers_for(make_user(db))
    foreign = client.post(URL, json=passport(), headers=other).json()
    assert client.get(URL, headers=customer_headers).json() == []
    response = client.delete(f"{URL}/{foreign['id']}", headers=customer_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Паспорт не знайдено"
    assert client.put(f"{URL}/{foreign['id']}", json=passport(), headers=customer_headers).status_code == 404
    assert len(client.get(URL, headers=other).json()) == 1


def test_access(client, db):
    assert client.get(URL).status_code == 401
    manager = headers_for(make_user(db, role=UserRole.MANAGER))
    assert client.get(URL, headers=manager).status_code == 403
    assert client.post(URL, json=passport(), headers=manager).status_code == 403
