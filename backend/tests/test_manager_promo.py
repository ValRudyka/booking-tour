"""Promo codes managed by managers (ТЗ 4.3, form 4.6.2.3)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, PromoCode
from app.models.enums import OrderStatus, PaymentStatus, UserRole
from app.services import clock
from tests.factories import headers_for, make_active_tour, make_order, make_paid_order, make_user

URL = "/api/manager/promo-codes"
TODAY = clock.today()


def body(**overrides):
    return {"code": "summer2027", "discount_type": "percent", "discount_value": "10",
            "valid_from": TODAY.isoformat(), "valid_to": (TODAY + timedelta(days=30)).isoformat()} | overrides


def create(client, headers, **overrides):
    return client.post(URL, json=body(**overrides), headers=headers)


def test_create_list_edit(client, db, manager, manager_headers):
    response = create(client, manager_headers, min_order_uah="5000", usage_limit=100)
    assert response.status_code == 201, response.text
    promo = response.json()
    assert (promo["code"], promo["discount_type"], promo["discount_value"], promo["usage_limit"],
            promo["is_active"], promo["used_count"], promo["paid_count"], promo["created_by"]) == (
        "SUMMER2027", "percent", "10.00", 100, True, 0, 0, manager.id)
    listed = client.get(URL, params={"q": "summer"}, headers=manager_headers).json()
    assert [p["code"] for p in listed["items"]] == ["SUMMER2027"]
    edited = client.patch(f"{URL}/{promo['id']}", json={"discount_value": "15", "usage_limit": None},
                          headers=manager_headers)
    assert edited.status_code == 200 and (edited.json()["discount_value"], edited.json()["usage_limit"]) == ("15.00", None)
    off = client.patch(f"{URL}/{promo['id']}", json={"is_active": False}, headers=manager_headers)
    assert off.json()["is_active"] is False
    assert [p["id"] for p in client.get(URL, params={"is_active": True}, headers=manager_headers).json()["items"]] == []
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity == "promo_code")
                         .order_by(AuditLog.id)).all()
    assert actions == ["created", "updated", "deactivated"]


@pytest.mark.parametrize("overrides, status", [
    ({"code": "ab1"}, 422), ({"code": "A" * 21}, 422), ({"code": "SUMMER-27"}, 422),
    ({"discount_value": "0"}, 422), ({"discount_value": "101"}, 422),
    ({"discount_type": "fixed", "discount_value": "0"}, 422),
    ({"discount_type": "fixed", "discount_value": "-5"}, 422),
    ({"valid_to": TODAY.isoformat()}, 422),                     # must be later than valid_from
    ({"usage_limit": 0}, 422), ({"min_order_uah": "-1"}, 422), ({"discount_type": "gift"}, 422),
    ({"used_count": 5}, 422),                                  # read-only
])
def test_rules(client, manager_headers, overrides, status):
    assert create(client, manager_headers, **overrides).status_code == status


def test_fixed_discount_and_unique_code(client, manager_headers):
    fixed = create(client, manager_headers, code="MINUS500", discount_type="fixed", discount_value="500")
    assert fixed.status_code == 201 and fixed.json()["discount_value"] == "500.00"
    assert create(client, manager_headers, code="minus500").status_code == 409
    other = create(client, manager_headers, code="OTHER123").json()
    assert client.patch(f"{URL}/{other['id']}", json={"code": "MINUS500"}, headers=manager_headers).status_code == 409


def test_used_code_cannot_be_deleted_or_renamed(client, db, customer, manager, manager_headers):
    promo = create(client, manager_headers).json()
    unused = create(client, manager_headers, code="UNUSED01").json()
    tour = make_active_tour(db, manager)
    paid = make_paid_order(db, customer, tour, promo_code_id=promo["id"])
    make_order(db, customer, tour, status=OrderStatus.CANCELLED, promo_code_id=promo["id"])
    detail = client.get(f"{URL}/{promo['id']}", headers=manager_headers).json()
    assert (detail["used_count"], detail["paid_count"]) == (1, 1)          # cancelled one does not hold a use

    refused = client.delete(f"{URL}/{promo['id']}", headers=manager_headers)
    assert refused.status_code == 409 and "деактивувати" in refused.json()["detail"]
    renamed = client.patch(f"{URL}/{promo['id']}", json={"code": "NEWNAME1"}, headers=manager_headers)
    assert renamed.status_code == 409 and "текст не змінюється" in renamed.json()["detail"]
    assert client.patch(f"{URL}/{promo['id']}", json={"is_active": False}, headers=manager_headers).status_code == 200
    db.refresh(paid)
    assert paid.promo_code_id == promo["id"]
    assert client.delete(f"{URL}/{unused['id']}", headers=manager_headers).status_code == 204
    assert db.get(PromoCode, unused["id"]) is None
    assert db.scalar(select(AuditLog).where(AuditLog.entity == "promo_code", AuditLog.action == "deleted"))
    assert PaymentStatus


def test_works_in_checkout(client, db, customer_headers, manager, manager_headers):
    tour = make_active_tour(db, manager, days_ahead=10, base_price=Decimal("1000"))
    promo = create(client, manager_headers, code="HOT2027", discount_value="20").json()
    quote = {"tour_id": tour.id, "start_date": tour.departure_from.isoformat(), "adults": 1,
             "promo_code": "hot2027"}
    priced = client.post("/api/orders/quote", json=quote, headers=customer_headers)
    assert priced.status_code == 200, priced.text
    assert Decimal(priced.json()["discount_uah"]) > 0 and priced.json()["promo_code"] == "HOT2027"
    client.patch(f"{URL}/{promo['id']}", json={"is_active": False}, headers=manager_headers)
    refused = client.post("/api/orders/quote", json=quote, headers=customer_headers)
    assert refused.status_code == 422 and "неактивний" in refused.json()["detail"]


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.CLIENT, UserRole.FINANCE])
def test_only_managers(client, db, manager_headers, role):
    promo = create(client, manager_headers).json()
    headers = headers_for(make_user(db, role=role))
    for call in (lambda h: client.get(URL, headers=h),
                 lambda h: client.post(URL, json=body(code="NOPE1234"), headers=h),
                 lambda h: client.patch(f"{URL}/{promo['id']}", json={"is_active": False}, headers=h),
                 lambda h: client.delete(f"{URL}/{promo['id']}", headers=h)):
        assert call(headers).status_code == 403
        assert call({}).status_code == 401
