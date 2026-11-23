"""Test data builders shared by all test modules (they only flush, the test transaction is rolled back)."""
from datetime import date, timedelta
from decimal import Decimal
from itertools import count

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import City, Country, Hotel, Order, Resort, Tour, User
from app.models.enums import Currency, TourStatus, TransportType, UserRole

_seq = count(1)


def make_user(db, phone=None, email=None, role=UserRole.CLIENT) -> User:
    n = next(_seq)
    user = User(phone=phone or f"+38050{n:07d}", email=email or f"user{n}@test.ua",
                password_hash="x", role=role, last_name="Шевченко", first_name="Тарас")
    db.add(user)
    db.flush()
    return user


def headers_for(user: User) -> dict[str, str]:
    """Bearer header without going through /login (no slow Argon2 hashing in every test)."""
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def resort(db, name_en: str) -> Resort:
    return db.scalar(select(Resort).where(Resort.name_en == name_en))


def city(db, name_en: str) -> City:
    return db.scalar(select(City).where(City.name_en == name_en))


def country(db, iso: str) -> Country:
    return db.scalar(select(Country).where(Country.iso_code == iso))


def make_hotel(db, name="Test Hotel", resort_en="Antalya", stars=5, rating=None, **overrides) -> Hotel:
    hotel = Hotel(resort_id=resort(db, resort_en).id, name=name, stars=stars,
                  rating_avg=Decimal(str(rating)) if rating is not None else None, **overrides)
    db.add(hotel)
    db.flush()
    return hotel


def make_tour(db, manager: User, **overrides) -> Tour:
    if "hotel_id" not in overrides:
        overrides["hotel_id"] = make_hotel(db).id
    fields = dict(title_uk="Тест", title_en="Test", transport_type=TransportType.NONE,
                  departure_from=date(2027, 6, 1), departure_to=date(2027, 6, 30), nights=7,
                  seats_total=10, base_price=Decimal("800.00"), currency=Currency.EUR,
                  created_by=manager.id)
    fields.update(overrides)
    tour = Tour(**fields)
    db.add(tour)
    db.flush()
    return tour


def make_active_tour(db, manager: User, days_ahead=30, **overrides) -> Tour:
    """An active tour whose departures start `days_ahead` days from today."""
    start = date.today() + timedelta(days=days_ahead)
    fields = dict(status=TourStatus.ACTIVE, departure_from=start, departure_to=start + timedelta(days=14))
    fields.update(overrides)
    return make_tour(db, manager, **fields)


def make_order(db, client: User, tour: Tour, **overrides) -> Order:
    n = next(_seq)
    fields = dict(number=f"TU-TEST-{n}", client_id=client.id, tour_id=tour.id,
                  start_date=date(2027, 6, 10), end_date=date(2027, 6, 17), adults=2,
                  total_uah=Decimal("77000.00"), rate_used=Decimal("48.0000"))
    fields.update(overrides)
    order = Order(**fields)
    db.add(order)
    db.flush()
    return order
