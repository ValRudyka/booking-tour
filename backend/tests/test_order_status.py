"""Order status model (ТЗ 4.4.1): transition table, history, quota accounting."""
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from sqlalchemy import select

from app.models import OrderStatusHistory, Tour, User
from app.models.enums import OrderStatus as S
from app.models.enums import UserRole
from app.services.errors import DomainError
from app.services.order_status import SOLD_STATUSES, TRANSITIONS, change_status, record_created
from tests.factories import make_order, make_tour, make_user

ALLOWED = [(old, new) for old, targets in TRANSITIONS.items() for new in sorted(targets)]
FORBIDDEN = [(old, new) for old, new in product(S, S) if new not in TRANSITIONS[old]]


def order_in(db, status, seats_total=10, adults=2, children=0):
    """An order of `adults + children` tourists in `status`, with the quota consistent with it."""
    manager = make_user(db, role=UserRole.MANAGER)
    tour = make_tour(db, manager, seats_total=seats_total)
    if status in SOLD_STATUSES:
        tour.seats_sold = adults + children
    hold = datetime.now(timezone.utc) + timedelta(minutes=20)
    return make_order(db, make_user(db), tour, status=status, adults=adults, children=children,
                      hold_expires_at=hold if status in (S.CHECKOUT, S.AWAITING_PAYMENT) else None)


def history(db, order):
    return db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
                      .order_by(OrderStatusHistory.id)).all()


def test_table_matches_tz():
    """Table 4.1 of the ТЗ, written out once more so an accidental edit is noticed."""
    assert {old: set(new) for old, new in TRANSITIONS.items()} == {
        S.CHECKOUT: {S.AWAITING_PAYMENT, S.CANCELLED},
        S.AWAITING_PAYMENT: {S.PAID, S.CANCELLED},
        S.PAID: {S.IN_PROGRESS, S.CANCEL_REQUESTED},
        S.IN_PROGRESS: {S.CONFIRMED, S.REJECTED, S.CANCEL_REQUESTED},
        S.CONFIRMED: {S.DOCUMENTS_READY, S.CANCEL_REQUESTED},
        S.DOCUMENTS_READY: {S.COMPLETED, S.CANCEL_REQUESTED},
        S.COMPLETED: {S.ARCHIVED},
        S.REJECTED: {S.ARCHIVED},
        S.CANCEL_REQUESTED: {S.CANCELLED},
        S.CANCELLED: {S.ARCHIVED},
        S.ARCHIVED: set(),
    }


@pytest.mark.parametrize("old,new", ALLOWED, ids=[f"{o.value}->{n.value}" for o, n in ALLOWED])
def test_allowed_transition_writes_history(db, old, new):
    order = order_in(db, old)
    actor = make_user(db, role=UserRole.MANAGER)
    change_status(db, order, new, actor, "коментар")
    assert order.status == new
    [row] = history(db, order)
    assert (row.old_status, row.new_status, row.changed_by, row.comment) == (
        old.value, new.value, actor.id, "коментар")


@pytest.mark.parametrize("old,new", FORBIDDEN, ids=[f"{o.value}->{n.value}" for o, n in FORBIDDEN])
def test_forbidden_transition_rejected(db, old, new):
    order = order_in(db, old)
    with pytest.raises(DomainError) as error:
        change_status(db, order, new, None)
    assert error.value.status_code == 409
    assert "Неможливо змінити статус замовлення" in error.value.message
    assert order.status == old
    assert history(db, order) == []


def test_system_change_has_no_author(db):
    order = order_in(db, S.CHECKOUT)
    change_status(db, order, S.CANCELLED, None, "Час на оплату минув")
    assert history(db, order)[0].changed_by is None


def test_record_created(db):
    order = order_in(db, S.CHECKOUT)
    client = db.get(User, order.client_id)
    record_created(db, order, client)
    [row] = history(db, order)
    assert (row.old_status, row.new_status, row.changed_by) == (None, "checkout", client.id)


def test_paid_writes_seats_off_the_quota(db):
    order = order_in(db, S.AWAITING_PAYMENT, adults=2, children=1)
    change_status(db, order, S.PAID, None)
    assert db.get(Tour, order.tour_id).seats_sold == 3


def test_paid_rechecks_free_seats(db):
    """The hold expired, someone else took the seats, the payment came late: no overselling."""
    order = order_in(db, S.AWAITING_PAYMENT, seats_total=3, adults=2)
    order.hold_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    other = make_order(db, make_user(db), db.get(Tour, order.tour_id), adults=2,
                       hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    assert other.status == S.CHECKOUT
    with pytest.raises(DomainError) as error:
        change_status(db, order, S.PAID, None)
    assert error.value.status_code == 409
    assert db.get(Tour, order.tour_id).seats_sold == 0
    assert order.status == S.AWAITING_PAYMENT


def test_own_hold_does_not_block_payment(db):
    order = order_in(db, S.AWAITING_PAYMENT, seats_total=2, adults=2)   # holds all seats
    change_status(db, order, S.PAID, None)
    assert db.get(Tour, order.tour_id).seats_sold == 2


@pytest.mark.parametrize("old,new", [(S.IN_PROGRESS, S.REJECTED), (S.CANCEL_REQUESTED, S.CANCELLED)])
def test_seats_return_after_rejection_or_cancellation(db, old, new):
    order = order_in(db, old, adults=2, children=2)
    assert db.get(Tour, order.tour_id).seats_sold == 4
    change_status(db, order, new, None)
    assert db.get(Tour, order.tour_id).seats_sold == 0


@pytest.mark.parametrize("old", [S.CHECKOUT, S.AWAITING_PAYMENT])
def test_cancel_before_payment_does_not_touch_seats_sold(db, old):
    order = order_in(db, old)
    change_status(db, order, S.CANCELLED, None)
    assert db.get(Tour, order.tour_id).seats_sold == 0
