"""Business dates are Kyiv dates (services/clock.py), whatever zone the server runs in.

The clock is frozen at 23:30 UTC on 24 Nov 2026: in Kyiv (UTC+2 in winter) it is already 25 Nov.
Code that used the server's or UTC's date would still see the 24th.
"""
import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models import AuditLog
from app.models.enums import TourStatus, UserRole
from app.services import clock
from tests.factories import add_payment, headers_for, make_order, make_tour, make_user

APP = Path(__file__).resolve().parent.parent / "app"
LATE_UTC = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)
KYIV_TODAY = date(2026, 11, 25)
DAY = timedelta(days=1)


def _local_clock_calls(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        owner_name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
        if owner_name == "date" and node.func.attr == "today":
            found.append(f"date.today() at line {node.lineno}")
        if owner_name == "datetime" and node.func.attr == "now" and not node.args and not node.keywords:
            found.append(f"naive datetime.now() at line {node.lineno}")
    return found


def test_app_never_reads_the_server_clock():
    """Use clock.today() / clock.now(): date.today() and datetime.now() are the server's zone."""
    offenders = {str(path.relative_to(APP)): calls
                 for path in sorted(APP.rglob("*.py"))
                 if (calls := _local_clock_calls(ast.parse(path.read_text(encoding="utf-8"))))}
    assert offenders == {}


@pytest.fixture()
def late_evening(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: LATE_UTC)
    assert clock.today() == KYIV_TODAY and clock.tomorrow() == KYIV_TODAY + DAY


def test_day_start_is_kyiv_midnight():
    assert clock.day_start(KYIV_TODAY) == datetime(2026, 11, 24, 22, 0, tzinfo=timezone.utc)


def test_catalog_lists_only_tours_with_a_bookable_date(client, db, manager, late_evening):
    """Booking starts tomorrow, so a tour on its last start day is no longer for sale."""
    last_day = make_tour(db, manager, status=TourStatus.ACTIVE, title_uk="Останній день",
                         departure_from=KYIV_TODAY - 10 * DAY, departure_to=KYIV_TODAY)
    bookable = make_tour(db, manager, status=TourStatus.ACTIVE, title_uk="Ще можна",
                         departure_from=KYIV_TODAY - 10 * DAY, departure_to=KYIV_TODAY + DAY)

    listed = [t["id"] for t in client.get("/api/tours", params={"page_size": 50}).json()["items"]]
    assert bookable.id in listed and last_day.id not in listed
    assert client.get(f"/api/tours/{last_day.id}").status_code == 404
    assert client.get(f"/api/tours/{bookable.id}").status_code == 200


def test_booking_starts_tomorrow_in_kyiv(client, db, manager, customer_headers, late_evening):
    tour = make_tour(db, manager, status=TourStatus.ACTIVE,
                     departure_from=KYIV_TODAY - 5 * DAY, departure_to=KYIV_TODAY + 20 * DAY)

    def quote(day: date):
        return client.post("/api/orders/quote", headers=customer_headers, json={
            "tour_id": tour.id, "start_date": day.isoformat(), "adults": 1, "children": 0})

    refused = quote(KYIV_TODAY)
    assert refused.status_code == 422 and "не раніше завтрашнього дня" in refused.text
    assert quote(KYIV_TODAY + DAY).status_code == 200


def test_publish_needs_a_start_date_from_tomorrow(client, db, manager, manager_headers, late_evening):
    tour = make_tour(db, manager, departure_from=KYIV_TODAY - 5 * DAY, departure_to=KYIV_TODAY)
    url = f"/api/manager/tours/{tour.id}/publish"
    refused = client.post(url, headers=manager_headers)
    assert refused.status_code == 422 and "минули" in refused.text

    client.patch(f"/api/manager/tours/{tour.id}", headers=manager_headers,
                 json={"departure_to": (KYIV_TODAY + DAY).isoformat()})
    assert client.post(url, headers=manager_headers).status_code == 200


def test_finance_register_filters_by_kyiv_day(client, db, customer, manager):
    """A payment at 23:30 UTC on the 24th was made on the 25th in Kyiv (the old UTC filter put it
    on the 24th, and the bank transfer test failed between 00:00 and 02:00 Kyiv time)."""
    tour = make_tour(db, manager, status=TourStatus.ACTIVE)
    payment = add_payment(db, make_order(db, customer, tour), "1000.00")
    payment.created_at = LATE_UTC
    db.flush()
    finance = headers_for(make_user(db, role=UserRole.FINANCE))

    def ids(day: date):
        response = client.get("/api/finance/payments", headers=finance,
                              params={"date_from": day.isoformat(), "date_to": day.isoformat()})
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    assert payment.id in ids(KYIV_TODAY)
    assert payment.id not in ids(KYIV_TODAY - DAY)


def test_audit_log_filters_by_kyiv_day(client, db):
    admin = make_user(db, role=UserRole.ADMIN)
    entry = AuditLog(user_id=admin.id, entity="settings", entity_id="1", action="updated",
                     created_at=LATE_UTC)
    db.add(entry)
    db.flush()

    def ids(day: date):
        response = client.get("/api/admin/audit-log", headers=headers_for(admin),
                              params={"date_from": day.isoformat(), "date_to": day.isoformat()})
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    assert entry.id in ids(KYIV_TODAY)
    assert entry.id not in ids(KYIV_TODAY - DAY)
