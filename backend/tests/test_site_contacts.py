"""Support contacts: set by the admin (form 4.6.4.1, fields 8–9), public at GET /api/site/contacts."""
import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.models.enums import UserRole
from tests.factories import headers_for, make_user

PUBLIC = "/api/site/contacts"
SETTINGS = "/api/admin/settings"


@pytest.fixture()
def admin_headers(db):
    return headers_for(make_user(db, role=UserRole.ADMIN))


def test_nothing_is_shown_until_the_admin_sets_it(client):
    assert client.get(PUBLIC).json() == {"phone": None, "email": None, "address": None}


def test_admin_sets_contacts_and_guests_see_them(client, db, admin_headers):
    response = client.put(SETTINGS, headers=admin_headers,
                          json={"support_phone": "+380 44 123 45 67", "support_email": " Help@Tour.Local "})
    assert response.status_code == 200, response.text
    assert (response.json()["support_phone"], response.json()["support_email"]) == ("+380441234567", "help@tour.local")
    assert client.get(PUBLIC).json() == {"phone": "+380441234567", "email": "help@tour.local", "address": None}

    entry = db.scalars(select(AuditLog).where(AuditLog.entity == "settings").order_by(AuditLog.id.desc())).first()
    assert entry.new_value == {"support_phone": "+380441234567", "support_email": "help@tour.local"}


def test_empty_values_remove_a_contact(client, admin_headers):
    client.put(SETTINGS, headers=admin_headers, json={"support_phone": "+380441234567", "support_email": "a@b.ua"})
    client.put(SETTINGS, headers=admin_headers, json={"support_phone": "", "support_email": ""})
    assert client.get(PUBLIC).json() == {"phone": None, "email": None, "address": None}


@pytest.mark.parametrize("field, value, message", [
    ("support_phone", "044 123", "«Телефон підтримки»: у міжнародному форматі, наприклад +380441234567"),
    ("support_email", "not-an-email", "«E-mail підтримки»: некоректна адреса"),
])
def test_invalid_contacts_are_refused(client, admin_headers, field, value, message):
    response = client.put(SETTINGS, headers=admin_headers, json={field: value})
    assert response.status_code == 422 and response.json()["detail"] == message


def test_only_the_admin_changes_them(client, db):
    manager = headers_for(make_user(db, role=UserRole.MANAGER))
    assert client.put(SETTINGS, headers=manager, json={"support_phone": "+380441234567"}).status_code == 403


def test_contacts_stay_available_in_maintenance_mode(client, admin_headers):
    client.put(SETTINGS, headers=admin_headers, json={"support_email": "help@tour.local", "maintenance_mode": True})
    assert client.get("/api/tours").status_code == 503
    response = client.get(PUBLIC)
    assert response.status_code == 200 and response.json()["email"] == "help@tour.local"
