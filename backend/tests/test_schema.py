"""The database itself must reject invalid data (CHECK, UNIQUE, FK constraints)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import (Base, Country, Hotel, Order, OrderStatusHistory, OrderTourist, Payment,
                        Resort, Review, Tour, User)
from app.models.enums import (Currency, OrderStatus, PaymentMethod, PaymentType, TourStatus,
                              TransportType, UserRole)


# ---------- helpers
def make_user(db, phone="+380501111111", email="client@test.ua", role=UserRole.CLIENT) -> User:
    user = User(phone=phone, email=email, password_hash="x", role=role,
                last_name="Шевченко", first_name="Тарас")
    db.add(user)
    db.flush()
    return user


def make_tour(db, manager: User, **overrides) -> Tour:
    resort = db.scalar(select(Resort).join(Country).where(Country.iso_code == "TR"))
    hotel = Hotel(resort_id=resort.id, name="Test Hotel", stars=5)
    db.add(hotel)
    db.flush()
    fields = dict(title_uk="Тест", title_en="Test", hotel_id=hotel.id,
                  transport_type=TransportType.NONE, departure_from=date(2027, 6, 1),
                  departure_to=date(2027, 6, 30), nights=7, seats_total=10,
                  base_price=Decimal("800.00"), currency=Currency.EUR, created_by=manager.id)
    fields.update(overrides)
    tour = Tour(**fields)
    db.add(tour)
    db.flush()
    return tour


def make_order(db, client: User, tour: Tour, **overrides) -> Order:
    fields = dict(number="TU-TEST-1", client_id=client.id, tour_id=tour.id,
                  start_date=date(2027, 6, 10), end_date=date(2027, 6, 17), adults=2,
                  total_uah=Decimal("77000.00"), rate_used=Decimal("48.0000"))
    fields.update(overrides)
    order = Order(**fields)
    db.add(order)
    db.flush()
    return order


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
    make_user(db)
    assert_rejected(db, lambda: make_user(db, email="other@test.ua"))


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
        db.add(Review(order_id=order.id, tour_id=tour.id, user_id=client.id,
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
