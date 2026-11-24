"""Separation of duties (ТЗ 4.3, 7: no single user gets every right): the administrator manages
users, reference data and settings, but cannot process orders, refunds, payments, reviews or promo
codes; other roles cannot use the admin endpoints."""
import pytest

from app.main import app
from app.models.enums import UserRole
from tests.factories import headers_for, make_user

OTHER_ROLE_ENDPOINTS = [
    ("GET", "/api/manager/orders"), ("POST", "/api/manager/orders/1/take"),
    ("POST", "/api/manager/orders/1/reject"), ("GET", "/api/manager/tours"),
    ("GET", "/api/manager/reviews"), ("POST", "/api/manager/reviews/1/publish"),
    ("GET", "/api/manager/promo-codes"), ("POST", "/api/manager/promo-codes"),
    ("GET", "/api/finance/payments"), ("POST", "/api/finance/payments/1/confirm"),
    ("GET", "/api/finance/refunds"), ("POST", "/api/finance/orders/1/refund"),
    ("GET", "/api/orders"), ("POST", "/api/orders"), ("GET", "/api/me/reviews"),
]


def admin_paths():
    """Every /api/admin route of the app (so a new admin endpoint is covered automatically)."""
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/admin"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, path.replace("{user_id}", "1").replace("{item_id}", "1").replace("{code}", "en")


@pytest.mark.parametrize("method, path", OTHER_ROLE_ENDPOINTS)
def test_admin_cannot_do_other_roles_work(client, db, method, path):
    admin = headers_for(make_user(db, role=UserRole.ADMIN))
    assert client.request(method, path, headers=admin).status_code == 403


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.FINANCE])
def test_admin_endpoints_only_for_admins(client, db, role):
    headers = headers_for(make_user(db, role=role))
    paths = list(admin_paths())
    assert len(paths) > 40
    for method, path in paths:
        assert client.request(method, path, headers=headers).status_code == 403, (method, path)
        assert client.request(method, path).status_code == 401, (method, path)
