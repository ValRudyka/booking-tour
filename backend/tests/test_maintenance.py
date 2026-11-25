"""Maintenance mode «Технічні роботи» (form 4.6.4.1, field 7): 503 except a short open list."""
import json

import pytest
from sqlalchemy import select

from app.config import settings as app_config
from app.core.security import hash_password
from app.models import AuditLog
from app.models.enums import UserRole
from app.services.payments.gateway import set_gateway
from app.services.payments.stripe_gateway import StripeGateway
from tests.factories import headers_for, make_active_tour, make_user, stripe_signature

MESSAGE = "Тривають технічні роботи. Спробуйте пізніше."


@pytest.fixture()
def admin(db):
    return make_user(db, role=UserRole.ADMIN)


@pytest.fixture()
def admin_headers(admin):
    return headers_for(admin)


@pytest.fixture()
def maintenance(client, admin_headers):
    response = client.put("/api/admin/settings", json={"maintenance_mode": True}, headers=admin_headers)
    assert response.status_code == 200 and response.json()["maintenance_mode"] is True
    return response


def with_password(db, role, phone):
    user = make_user(db, role=role, phone=phone)
    user.password_hash = hash_password("Some-pass-11")
    db.flush()
    return user


def login(client, phone):
    return client.post("/api/auth/login", data={"username": phone, "password": "Some-pass-11"})


def assert_down(response):
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == MESSAGE and response.headers["retry-after"] == "600"


def test_clients_and_guests_get_503(client, db, manager, customer_headers, maintenance):
    tour = make_active_tour(db, manager)
    assert_down(client.get("/api/tours"))
    assert_down(client.get(f"/api/tours/{tour.id}"))
    assert_down(client.get("/api/reference/countries"))
    assert_down(client.get("/api/orders", headers=customer_headers))
    assert_down(client.post("/api/orders", json={"tour_id": tour.id}, headers=customer_headers))
    assert_down(client.post("/api/auth/register", json={}))
    assert_down(client.get("/api/auth/me", headers=customer_headers))


def test_only_admin_login_works(client, db, maintenance):
    with_password(db, UserRole.CLIENT, "+380501110001")
    with_password(db, UserRole.MANAGER, "+380501110002")
    with_password(db, UserRole.FINANCE, "+380501110003")
    with_password(db, UserRole.ADMIN, "+380501110004")
    # Managers and finance would get a token every other endpoint refuses (the frontend then
    # looped back to /login), so they are refused here like clients.
    assert_down(login(client, "+380501110001"))
    assert_down(login(client, "+380501110002"))
    assert_down(login(client, "+380501110003"))
    admin = login(client, "+380501110004")
    assert admin.status_code == 200 and admin.json()["user"]["role"] == "admin"
    # Wrong password is still 401, not a hint that the account exists.
    assert client.post("/api/auth/login", data={"username": "+380501110001", "password": "x" * 9}
                       ).status_code == 401


def test_staff_other_than_admin_are_stopped_too(client, db, manager_headers, maintenance):
    finance = headers_for(make_user(db, role=UserRole.FINANCE))
    assert_down(client.get("/api/manager/orders", headers=manager_headers))
    assert_down(client.get("/api/finance/payments", headers=finance))
    assert_down(client.get("/api/auth/me", headers=manager_headers))


def test_admin_keeps_working_and_switches_it_off(client, db, admin, admin_headers, customer_headers, maintenance):
    assert client.get("/api/auth/me", headers=admin_headers).json()["id"] == admin.id
    assert client.get("/api/admin/users", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/audit-log", headers=admin_headers).status_code == 200
    off = client.put("/api/admin/settings", json={"maintenance_mode": False}, headers=admin_headers)
    assert off.status_code == 200 and off.json()["maintenance_mode"] is False
    assert client.get("/api/tours").status_code == 200
    assert client.get("/api/orders", headers=customer_headers).status_code == 200
    actions = db.scalars(select(AuditLog.new_value).where(AuditLog.entity == "settings").order_by(AuditLog.id)).all()
    assert actions == [{"maintenance_mode": True}, {"maintenance_mode": False}]


def test_open_paths(client, maintenance):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    # Admin paths are not opened to others: they still need the admin role.
    assert client.get("/api/admin/settings").status_code == 401


def test_stripe_webhook_still_processed(client, maintenance):
    secret = "whsec_maintenance"
    body = json.dumps({"id": "evt_m", "object": "event", "type": "charge.refunded",
                       "data": {"object": {"id": "ch_1", "object": "charge"}}}).encode()
    set_gateway(StripeGateway("sk_test_dummy_not_used", secret, app_config.stripe_api_version))
    response = client.post("/api/payments/stripe/webhook", content=body,
                           headers={"Stripe-Signature": stripe_signature(body, secret),
                                    "Content-Type": "application/json"})
    assert response.status_code == 200 and response.json()["result"] == "ignored"


def test_off_by_default(client):
    assert client.get("/api/tours").status_code == 200
