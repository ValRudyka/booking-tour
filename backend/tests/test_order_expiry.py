"""Orders with an expired seat hold are cancelled by the System (ТЗ 4.4.1, 4.5.3 step 9)."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import settings
from app.models.enums import OrderStatus as S
from app.services.order_expiry import expire_orders
from scripts import expire_orders as expire_cli
from tests.factories import make_order, make_tour, make_user

NOW = datetime.now(timezone.utc)


def test_expire_orders_cancels_only_expired_holds(db, manager):
    tour = make_tour(db, manager)
    client = make_user(db)
    past, future = NOW - timedelta(minutes=1), NOW + timedelta(minutes=10)
    expired = [make_order(db, client, tour, status=S.CHECKOUT, hold_expires_at=past),
               make_order(db, client, tour, status=S.AWAITING_PAYMENT, hold_expires_at=past)]
    kept = [make_order(db, client, tour, status=S.CHECKOUT, hold_expires_at=future),
            make_order(db, client, tour, status=S.AWAITING_PAYMENT, hold_expires_at=future)]
    tour.seats_sold = 2
    paid = make_order(db, client, tour, status=S.PAID, hold_expires_at=past)   # not a hold anymore

    assert expire_orders(db) == 2
    for order, old in zip(expired, ["checkout", "awaiting_payment"]):
        assert order.status == S.CANCELLED
        last = order.history[-1]
        assert (last.old_status, last.new_status, last.changed_by, last.comment) == (
            old, "cancelled", None, "Час на оплату минув")
    assert [o.status for o in kept] == [S.CHECKOUT, S.AWAITING_PAYMENT]
    assert paid.status == S.PAID and tour.seats_sold == 2
    assert expire_orders(db) == 0          # nothing left to do on the next run


def test_cli_prints_the_count(monkeypatch, capsys):
    monkeypatch.setattr(expire_cli, "run_expiry_job", lambda: 3)
    assert expire_cli.main() == 0
    assert "Cancelled orders with an expired seat hold: 3" in capsys.readouterr().out


def test_lifespan_runs_the_job_periodically(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "run_expiry_job", lambda: calls.append(1) or 0)
    monkeypatch.setattr(settings, "order_expiry_interval_sec", 0.01)
    with TestClient(main_module.app):
        deadline = datetime.now() + timedelta(seconds=2)
        while len(calls) < 3 and datetime.now() < deadline:
            asyncio.run(asyncio.sleep(0.01))
    assert len(calls) >= 3
    stopped_at = len(calls)
    asyncio.run(asyncio.sleep(0.05))
    assert len(calls) == stopped_at        # the loop stops with the app


def test_loop_survives_a_failing_job(monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        raise RuntimeError("database is down")

    monkeypatch.setattr(main_module, "run_expiry_job", flaky)
    monkeypatch.setattr(settings, "order_expiry_interval_sec", 0.01)
    with TestClient(main_module.app):
        deadline = datetime.now() + timedelta(seconds=2)
        while len(calls) < 2 and datetime.now() < deadline:
            asyncio.run(asyncio.sleep(0.01))
    assert len(calls) >= 2


def test_loop_is_off_in_tests():
    assert settings.order_expiry_interval_sec == 0
