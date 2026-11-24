"""Test data builders shared by all test modules (they only flush, the test transaction is rolled back)."""
from datetime import date, timedelta
from decimal import Decimal
from itertools import count

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import (City, Country, CurrencyRate, Hotel, Order, OrderTourist, Payment, PromoCode,
                        Resort, Tour, User)
from app.models.enums import (Currency, DiscountType, OrderStatus, PaymentMethod, PaymentStatus,
                              PaymentType, TourStatus, TransactionStatus, TransportType, UserRole)

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


def add_payment(db, order: Order, amount, method=PaymentMethod.CARD, intent: str | None = None,
                received_at=None) -> Payment:
    """A succeeded incoming payment (card: with a PaymentIntent, so it can be refunded)."""
    from datetime import datetime, timezone

    amount = Decimal(str(amount))
    payment = Payment(order_id=order.id, type=PaymentType.PAYMENT, method=method,
                      status=TransactionStatus.SUCCEEDED, amount_uah=amount, paid_amount=amount,
                      received_at=received_at or datetime.now(timezone.utc),
                      stripe_payment_intent=(intent or f"pi_test_{order.id}_{next(_seq)}")
                      if method == PaymentMethod.CARD else None)
    db.add(payment)
    db.flush()
    return payment


def make_paid_order(db, client: User, tour: Tour, status=OrderStatus.PAID, total="77000.00",
                    payments: list | None = None, **overrides) -> Order:
    """An order that went through checkout and was paid: seats sold, one tourist per seat,
    succeeded payments (default: one card payment of the whole total)."""
    overrides.setdefault("adults", 2)
    order = make_order(db, client, tour, status=status, payment_status=PaymentStatus.PAID,
                       total_uah=Decimal(total), offer_accepted_at=None, **overrides)
    for i in range(order.adults + order.children):
        db.add(OrderTourist(order_id=order.id, last_name_lat="Shevchenko", first_name_lat=f"Taras{i}",
                            birth_date=date(1990, 1, 1), passport_number=f"FX{100000 + i}",
                            passport_expiry=date.today() + timedelta(days=3 * 365)))
    tour.seats_sold += order.adults + order.children
    for amount, method in payments or [(total, PaymentMethod.CARD)]:
        add_payment(db, order, amount, method)
    db.flush()
    db.refresh(order)
    return order


def make_promo(db, code="SUMMER", discount_type=DiscountType.PERCENT, value="10", min_order=None,
               valid_from=None, valid_to=None, usage_limit=None, is_active=True) -> PromoCode:
    today = date.today()
    promo = PromoCode(code=code, discount_type=discount_type, discount_value=Decimal(value),
                      min_order_uah=Decimal(min_order) if min_order is not None else None,
                      valid_from=valid_from or today - timedelta(days=1),
                      valid_to=valid_to or today + timedelta(days=30), usage_limit=usage_limit,
                      is_active=is_active, created_by=make_user(db, role=UserRole.ADMIN).id)
    db.add(promo)
    db.flush()
    return promo


def set_rate(db, currency: Currency, rate: str) -> None:
    db.get(CurrencyRate, currency).rate_to_uah = Decimal(rate)
    db.flush()


def tourist(birth_date: date, last="Shevchenko", first="Taras", passport="FX123456",
            expiry: date | None = None) -> dict:
    return {"last_name_lat": last, "first_name_lat": first, "birth_date": birth_date.isoformat(),
            "passport_number": passport,
            "passport_expiry": (expiry or date.today() + timedelta(days=3 * 365)).isoformat()}


def years_before(day: date, years: int, plus_days: int = 0) -> date:
    """The date `years` years before `day` (29 Feb -> 28 Feb), shifted by `plus_days`."""
    try:
        result = day.replace(year=day.year - years)
    except ValueError:
        result = day.replace(year=day.year - years, day=28)
    return result + timedelta(days=plus_days)


def stripe_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """A `Stripe-Signature` header computed like Stripe does (HMAC-SHA256 of "t.payload")."""
    import hashlib
    import hmac
    import time

    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"
