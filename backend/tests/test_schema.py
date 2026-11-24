"""The database itself must reject invalid data (CHECK, UNIQUE, FK constraints)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Base, Country, OrderStatusHistory, OrderTourist, Payment, Review
from app.models.enums import (OrderStatus, PaymentMethod, PaymentType, TourStatus, TransportType,
                              UserRole)
from tests.factories import make_order, make_tour, make_user


# ---------- helpers
def assert_rejected(db, fn):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            fn()


# ---------- structure
def test_all_tables_created(db):
    tables = set(inspect(db.connection()).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert len(Base.metadata.tables) == 27


def test_reference_data_loaded(db):
    assert db.scalar(select(func.count()).select_from(Country)) == 13
    assert db.execute(text("SELECT value FROM settings WHERE key = 'booking_timeout_min'")).scalar() == 20


# ---------- happy path
def test_full_order_graph_and_cascade(db):
    manager = make_user(db, "+380502222222", "manager@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager, status=TourStatus.ACTIVE)
    order = make_order(db, client, tour)
    order.tourists.append(OrderTourist(last_name_lat="SHEVCHENKO", first_name_lat="TARAS",
                                       birth_date=date(1990, 3, 9), passport_number="FA123456",
                                       passport_expiry=date(2030, 1, 1)))
    order.history.append(OrderStatusHistory(old_status=None, new_status=OrderStatus.CHECKOUT.value))
    db.add(Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                   amount_uah=Decimal("77000.00")))
    db.flush()
    assert order.status == OrderStatus.CHECKOUT  # server default
    # deleting the order removes its tourists and history (ON DELETE CASCADE / ORM cascade)
    order_id = order.id
    db.query(Payment).filter_by(order_id=order_id).delete()
    db.delete(order)
    db.flush()
    assert db.scalar(select(func.count()).select_from(OrderTourist).where(
        OrderTourist.order_id == order_id)) == 0


# ---------- constraints
def test_duplicate_phone_rejected(db):
    make_user(db, phone="+380501111111")
    assert_rejected(db, lambda: make_user(db, phone="+380501111111", email="other@test.ua"))


def test_unknown_role_rejected(db):
    assert_rejected(db, lambda: db.execute(text(
        "INSERT INTO users (phone, email, password_hash, role, last_name, first_name) "
        "VALUES ('+1', 'a@b.c', 'x', 'superuser', 'A', 'B')")))


def test_tour_quota_cannot_be_oversold(db):
    manager = make_user(db, role=UserRole.MANAGER)
    tour = make_tour(db, manager)
    tour.seats_sold = 11  # seats_total = 10

    assert_rejected(db, db.flush)


def test_tour_nights_range(db):
    manager = make_user(db, role=UserRole.MANAGER)
    assert_rejected(db, lambda: make_tour(db, manager, nights=31))


def test_departure_city_required_for_air(db):
    manager = make_user(db, role=UserRole.MANAGER)
    assert_rejected(db, lambda: make_tour(db, manager, transport_type=TransportType.AIR))


def test_order_needs_an_adult(db):
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager)
    assert_rejected(db, lambda: make_order(db, client, tour, adults=0))


def test_order_dates_order(db):
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager)
    assert_rejected(db, lambda: make_order(db, client, tour,
                                           end_date=date(2027, 6, 10) - timedelta(days=1)))


def test_unknown_order_status_rejected(db):
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager)
    order = make_order(db, client, tour)
    assert_rejected(db, lambda: db.execute(
        text("UPDATE orders SET status = 'teleported' WHERE id = :id"), {"id": order.id}))


def test_review_rating_range_and_one_per_order(db):
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager)
    order = make_order(db, client, tour)

    def review(rating=5):
        db.add(Review(order_id=order.id, tour_id=tour.id, hotel_id=tour.hotel_id, user_id=client.id,
                      hotel_rating=rating, service_rating=5))
        db.flush()

    assert_rejected(db, lambda: review(6))
    review(5)
    assert_rejected(db, review)  # second review for the same order


def test_payment_amount_positive(db):
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    order = make_order(db, client, make_tour(db, manager))

    def pay():
        db.add(Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                       amount_uah=Decimal("0")))
        db.flush()

    assert_rejected(db, pay)


def test_refund_links_fpv_and_cancel_reason(db):
    """Migration 'refunds and cancellation requests': only refunds point at a payment, ФПВ is
    never negative, the cancellation reason comes from the list, Stripe refund ids are unique."""
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    order = make_order(db, make_user(db), make_tour(db, manager))
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                      amount_uah=Decimal("100"))
    db.add(payment)
    db.flush()

    def row(kind, refund_of=None, refund_id=None):
        db.add(Payment(order_id=order.id, type=kind, method=PaymentMethod.CARD,
                       amount_uah=Decimal("10"), refund_of_id=refund_of, stripe_refund_id=refund_id))
        db.flush()

    assert_rejected(db, lambda: row(PaymentType.PAYMENT, refund_of=payment.id))
    row(PaymentType.REFUND, refund_of=payment.id, refund_id="re_1")
    assert_rejected(db, lambda: row(PaymentType.REFUND, refund_of=payment.id, refund_id="re_1"))
    assert_rejected(db, lambda: db.execute(
        text("UPDATE orders SET fpv_uah = -1 WHERE id = :id"), {"id": order.id}))
    assert_rejected(db, lambda: db.execute(
        text("UPDATE orders SET cancel_reason_code = 'bored' WHERE id = :id"), {"id": order.id}))
    db.execute(text("UPDATE orders SET cancel_reason_code = 'illness', fpv_uah = 0 WHERE id = :id"),
               {"id": order.id})


def test_review_status_and_hotel_required(db):
    """Migration 'review moderation': status from the list, hotel_id required."""
    manager = make_user(db, "+380502222222", "m@test.ua", UserRole.MANAGER)
    client = make_user(db)
    tour = make_tour(db, manager)
    order = make_order(db, client, tour)

    def review(**fields):
        db.add(Review(order_id=order.id, tour_id=tour.id, user_id=client.id, hotel_rating=5,
                      service_rating=5, **fields))
        db.flush()

    assert_rejected(db, lambda: review(hotel_id=None))
    review(hotel_id=tour.hotel_id)
    assert_rejected(db, lambda: db.execute(text("UPDATE reviews SET status = 'hidden'")))
    assert db.execute(text("SELECT value FROM settings WHERE key = 'review_premoderation'")).scalar() is True


def test_single_default_service_and_append_only_audit_log(db):
    """Migration 'admin': one default insurance/transfer type; audit_log refuses UPDATE/DELETE."""
    from app.models import AuditLog, InsuranceType, TransferType

    for model in (InsuranceType, TransferType):
        assert db.query(model).filter(model.is_default.is_(True)).count() == 1
        assert_rejected(db, lambda: (db.add(model(name_uk="Ще один", price_uah=Decimal("1"),
                                                  is_default=True)), db.flush()))
    entry = AuditLog(user_id=None, entity="test", entity_id="1", action="created")
    db.add(entry)
    db.flush()
    from sqlalchemy.exc import DBAPIError

    for statement in ("UPDATE audit_log SET action = 'changed' WHERE id = :id",
                      "DELETE FROM audit_log WHERE id = :id"):
        with pytest.raises(DBAPIError, match="append-only"):
            with db.begin_nested():
                db.execute(text(statement), {"id": entry.id})
