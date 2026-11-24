"""«Завершено» after the trip (ТЗ 4.4 step 10, table 4.1): the System completes «Документи готові»
orders the day after end_date (Kyiv date); other statuses are only reported."""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main as main_module
from app.config import settings
from app.models import Notification, Order
from app.models.enums import OrderStatus as S
from app.services import clock
from app.services.order_completion import complete_orders
from scripts import complete_orders as complete_cli
from tests.factories import make_active_tour, make_paid_order

TODAY = date(2027, 6, 18)


def order_ending(db, customer, tour, end: date, status=S.DOCUMENTS_READY):
    return make_paid_order(db, customer, tour, status=status, start_date=end - timedelta(days=7), end_date=end)


def test_completes_documents_ready_after_the_end_date(db, customer, manager, caplog):
    tour = make_active_tour(db, manager)
    ended = order_ending(db, customer, tour, TODAY - timedelta(days=1))       # back yesterday
    today = order_ending(db, customer, tour, TODAY)                            # back today
    later = order_ending(db, customer, tour, TODAY + timedelta(days=1))
    confirmed = order_ending(db, customer, tour, TODAY - timedelta(days=3), status=S.CONFIRMED)
    requested = order_ending(db, customer, tour, TODAY - timedelta(days=3), status=S.CANCEL_REQUESTED)

    with caplog.at_level(logging.WARNING, logger="tour.orders"):
        assert complete_orders(db, TODAY) == 1
    db.expire_all()
    done = db.get(Order, ended.id)
    assert done.status == S.COMPLETED
    assert (done.history[-1].changed_by, done.history[-1].comment) == (None, "Подорож завершено")
    assert [db.get(Order, o.id).status for o in (today, later, confirmed, requested)] == [
        S.DOCUMENTS_READY, S.DOCUMENTS_READY, S.CONFIRMED, S.CANCEL_REQUESTED]
    warning = caplog.records[-1].getMessage()
    assert confirmed.number in warning and requested.number not in warning
    note = db.scalars(select(Notification).where(Notification.order_id == ended.id)).one()
    assert note.user_id == customer.id and "відгук" in note.body
    assert complete_orders(db, TODAY) == 0                                     # nothing left


def test_business_date_is_kyiv():
    late_evening_utc = datetime(2026, 11, 24, 22, 30, tzinfo=timezone.utc)     # 00:30 in Kyiv
    assert clock.today(late_evening_utc) == date(2026, 11, 25)
    assert settings.business_timezone == "Europe/Kyiv"


def test_cli(monkeypatch, capsys):
    monkeypatch.setattr(complete_cli, "run_completion_job", lambda: 2)
    assert complete_cli.main() == 0
    assert "Completed orders (trip ended, documents ready): 2" in capsys.readouterr().out


def test_lifespan_runs_the_completion_job(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "run_completion_job", lambda: calls.append(1) or 0)
    monkeypatch.setattr(settings, "order_completion_interval_sec", 0.01)
    with TestClient(main_module.app):
        deadline = datetime.now() + timedelta(seconds=2)
        while len(calls) < 2 and datetime.now() < deadline:
            asyncio.run(asyncio.sleep(0.01))
    assert len(calls) >= 2


def test_completion_loop_is_off_in_tests():
    assert settings.order_completion_interval_sec == 0
