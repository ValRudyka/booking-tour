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
            "expiry_date": (clock.today() + timedelta(days=700)).isoformat()}
    return data | overrides


def test_add_list_delete(client, customer_headers):
    response = client.post(URL, json=passport(), headers=customer_headers)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["passport_number"] == "FX123456"          # spaces removed, upper case
    client.post(URL, json=passport(first_name_lat="Olena", issuing_authority=None),
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
])
def test_validation(client, customer_headers, overrides, message):
    response = client.post(URL, json=passport(**overrides), headers=customer_headers)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_only_own_passports(client, db, customer_headers):
    other = headers_for(make_user(db))
    foreign = client.post(URL, json=passport(), headers=other).json()
    assert client.get(URL, headers=customer_headers).json() == []
    response = client.delete(f"{URL}/{foreign['id']}", headers=customer_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Паспорт не знайдено"
    assert len(client.get(URL, headers=other).json()) == 1


def test_access(client, db):
    assert client.get(URL).status_code == 401
    manager = headers_for(make_user(db, role=UserRole.MANAGER))
    assert client.get(URL, headers=manager).status_code == 403
    assert client.post(URL, json=passport(), headers=manager).status_code == 403
