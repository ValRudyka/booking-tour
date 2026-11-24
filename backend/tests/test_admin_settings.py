"""Administrator: global settings (form 4.6.4.1), payment gateway status, audit log viewer."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings as app_config
from app.models import AuditLog, CurrencyRate, Order, Setting
from app.models.enums import Currency, OrderStatus, UserRole
from tests.factories import headers_for, make_active_tour, make_order, make_paid_order, make_user

URL = "/api/admin/settings"


@pytest.fixture()
def admin(db):
    return make_user(db, role=UserRole.ADMIN)


@pytest.fixture()
def admin_headers(admin):
    return headers_for(admin)


def put(client, headers, **values):
    return client.put(URL, json=values, headers=headers)


def test_read_settings(client, admin_headers):
    body = client.get(URL, headers=admin_headers).json()
    assert body["uah_rate"] == "1" and body["booking_timeout_min"] == 20
    assert body["review_premoderation"] is True and body["maintenance_mode"] is False
    assert Decimal(body["eur_rate"]) > 0 and "booking_timeout_min" in body["changes"]


def test_update_and_audit(client, db, admin, admin_headers):
    response = put(client, admin_headers, eur_rate="49.1250", acquiring_percent="2.75",
                   system_email="Info@Tour.ua", review_premoderation=False)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["eur_rate"], body["acquiring_percent"], body["system_email"], body["review_premoderation"]) == (
        "49.1250", "2.75", "info@tour.ua", False)
    assert body["changes"]["eur_rate"]["updated_by"] == admin.id
    assert db.get(Setting, "system_email").updated_by == admin.id
    [entry] = db.scalars(select(AuditLog).where(AuditLog.entity == "settings")).all()
    assert entry.user_id == admin.id
    assert entry.new_value == {"eur_rate": "49.1250", "acquiring_percent": "2.75",
                               "system_email": "info@tour.ua", "review_premoderation": False}
    assert entry.old_value["review_premoderation"] is True
    # Nothing changed -> no new audit row.
    put(client, admin_headers, eur_rate="49.125")
    assert db.scalar(select(AuditLog).where(AuditLog.entity == "settings", AuditLog.id != entry.id)) is None


@pytest.mark.parametrize("field, value", [
    ("eur_rate", "0"), ("eur_rate", "-1"), ("usd_rate", "10001"), ("usd_rate", "41.12345"),
    ("acquiring_percent", "10.01"), ("acquiring_percent", "1.234"), ("booking_timeout_min", 4),
    ("booking_timeout_min", 121), ("bank_transfer_hold_hours", 0), ("bank_transfer_hold_hours", 169),
    ("system_email", "not-an-email"), ("maintenance_mode", "maybe"), ("uah_rate", "2"),
])
def test_validation(client, db, admin_headers, field, value):
    response = put(client, admin_headers, **{field: value})
    assert response.status_code == 422, response.text
    assert db.scalar(select(AuditLog).where(AuditLog.entity == "settings")) is None


def test_rates_do_not_change_placed_orders(client, db, customer, manager, admin_headers):
    tour = make_active_tour(db, manager)                        # EUR 800
    before = client.get(f"/api/tours/{tour.id}").json()["price_from_uah"]
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT,
                         total_uah=Decimal("77000.00"), rate_used=Decimal("48.0000"))
    paid = make_paid_order(db, customer, tour, rate_used=Decimal("48.0000"))
    put(client, admin_headers, eur_rate="55.0000")
    assert client.get(f"/api/tours/{tour.id}").json()["price_from_uah"] != before   # catalog uses it
    assert client.get(f"/api/tours/{tour.id}").json()["price_from_uah"] == "44000.00"
    db.expire_all()
    for order in (waiting, paid):
        frozen = db.get(Order, order.id)
        assert (frozen.total_uah, frozen.rate_used) == (Decimal("77000.00"), Decimal("48.0000"))
    assert db.get(CurrencyRate, Currency.UAH).rate_to_uah == Decimal("1.0000")


def test_new_booking_timeout_applies_to_new_orders(client, db, customer, customer_headers, manager,
                                                  admin_headers):
    tour = make_active_tour(db, manager, days_ahead=10)
    old = make_order(db, customer, tour, status=OrderStatus.CHECKOUT,
                     hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=20))
    put(client, admin_headers, booking_timeout_min=45)
    created = client.post("/api/orders", json={"tour_id": tour.id, "start_date": tour.departure_from.isoformat(),
                                               "adults": 1}, headers=customer_headers)
    assert created.status_code == 201, created.text
    hold = datetime.fromisoformat(created.json()["hold_expires_at"])
    assert timedelta(minutes=44) < hold - datetime.now(timezone.utc) <= timedelta(minutes=45)
    db.refresh(old)
    assert old.hold_expires_at - datetime.now(timezone.utc) < timedelta(minutes=21)   # untouched


def test_gateway_status_shows_no_secrets(client, admin_headers, monkeypatch):
    monkeypatch.setattr(app_config, "stripe_secret_key", "sk_test_SUPERSECRET123")
    monkeypatch.setattr(app_config, "stripe_webhook_secret", "whsec_SUPERSECRET456")
    response = client.get("/api/admin/payment-gateway", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["gateway"], body["stripe_key_configured"], body["stripe_key_mode"],
            body["webhook_secret_configured"]) == ("mock", True, "test", True)
    assert "SUPERSECRET" not in response.text


# ---------- audit log viewer
def test_audit_log_filters(client, db, admin, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER)
    client.patch(f"/api/admin/users/{manager.id}", json={"is_active": False}, headers=admin_headers)
    put(client, admin_headers, booking_timeout_min=30)
    other_admin = make_user(db, role=UserRole.ADMIN)
    client.put(URL, json={"booking_timeout_min": 25}, headers=headers_for(other_admin))

    def get(**params):
        return client.get("/api/admin/audit-log", params=params, headers=admin_headers).json()

    everything = get()
    assert everything["total"] >= 3 and everything["items"][0]["new_value"] == {"booking_timeout_min": 25}
    assert [e["action"] for e in get(entity="user", entity_id=str(manager.id))["items"]] == ["blocked"]
    assert get(action="blocked")["items"][0]["entity_id"] == str(manager.id)
    assert {e["user_id"] for e in get(entity="settings")["items"]} == {admin.id, other_admin.id}
    assert get(entity="settings", user_id=other_admin.id)["total"] == 1
    today = datetime.now(timezone.utc).date()
    assert get(date_from=today.isoformat(), date_to=today.isoformat())["total"] == everything["total"]
    assert get(date_to=(today - timedelta(days=1)).isoformat(), entity="settings")["total"] == 0
    assert len(get(page_size=1)["items"]) == 1


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.FINANCE])
def test_settings_only_for_admins(client, db, role):
    headers = headers_for(make_user(db, role=role))
    for call in (lambda h: client.get(URL, headers=h),
                 lambda h: client.put(URL, json={"booking_timeout_min": 30}, headers=h),
                 lambda h: client.get("/api/admin/payment-gateway", headers=h),
                 lambda h: client.get("/api/admin/audit-log", headers=h)):
        assert call(headers).status_code == 403
        assert call({}).status_code == 401
    assert db.get(Setting, "booking_timeout_min").value == 20
