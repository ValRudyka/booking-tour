"""Order price (form 4.6.1.2, field 8) and promo codes (form 4.6.2.3), via POST /api/orders/quote.

Seeded data: rates EUR 48, USD 42, UAH 1; insurance «Базове» 350 (default) / «Розширене» 700 per
tourist; transfer «Груповий» 0 (default) / «Індивідуальний» 2500 per order.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import InsuranceType, Order, TransferType
from app.models.enums import Currency, DiscountType, OrderStatus
from app.services.pricing import age_on, is_child
from tests.factories import (make_active_tour, make_order, make_promo, make_user, set_rate,
                             years_before)

URL = "/api/orders/quote"
START = date.today() + timedelta(days=12)


@pytest.fixture()
def tour(db, manager):
    """EUR tour: adult 800, child 400; departures today+10 .. today+24."""
    return make_active_tour(db, manager, days_ahead=10, base_price=Decimal("800"),
                            child_price=Decimal("400"), currency=Currency.EUR)


def option_id(db, model, name):
    return db.scalar(select(model.id).where(model.name_uk == name))


def quote(client, headers, tour, adults=2, children=0, **extra):
    body = {"tour_id": tour.id, "start_date": START.isoformat(), "adults": adults,
            "children": children} | extra
    return client.post(URL, json=body, headers=headers)


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def error(response, status=422) -> str:
    assert response.status_code == status, response.text
    return response.json()["detail"]


# ---------- age
@pytest.mark.parametrize("birth,expected", [
    (date(2015, 6, 10), 12), (date(2015, 6, 11), 11), (date(2016, 2, 29), 11),
])
def test_age_on(birth, expected):
    assert age_on(birth, date(2027, 6, 10)) == expected


def test_child_is_under_12_on_start_date():
    assert is_child(years_before(START, 12, plus_days=1), START)       # 11 years 364 days
    assert not is_child(years_before(START, 12), START)                # exactly 12 = adult


# ---------- formula
def test_adults_only(client, customer_headers, tour):
    price = ok(quote(client, customer_headers, tour, adults=2))
    assert price["tour_uah"] == "76800.00"            # 800 × 2 × 48
    assert price["insurance_name"] == "Базове"
    assert price["insurance_uah"] == "700.00"         # 350 × 2
    assert price["transfer_name"] == "Груповий" and price["transfer_uah"] == "0.00"
    assert price["subtotal_uah"] == price["total_uah"] == "77500.00"
    assert (price["rate"], price["currency"], price["discount_uah"]) == ("48.0000", "EUR", "0.00")


def test_adults_and_children(client, customer_headers, tour):
    price = ok(quote(client, customer_headers, tour, adults=2, children=1))
    assert price["child_price"] == "400.00"
    assert price["tour_uah"] == "96000.00"            # (800×2 + 400×1) × 48
    assert price["insurance_uah"] == "1050.00"        # 350 × 3 tourists
    assert price["total_uah"] == "97050.00"


def test_child_price_null_means_adult_price(client, db, customer_headers, tour):
    tour.child_price = None
    db.flush()
    price = ok(quote(client, customer_headers, tour, adults=1, children=1))
    assert price["child_price"] == "800.00"
    assert price["tour_uah"] == "76800.00"


@pytest.mark.parametrize("currency,base,expected_tour_uah", [
    (Currency.EUR, "800", "38400.00"), (Currency.USD, "900", "37800.00"),
    (Currency.UAH, "25000", "25000.00"),
])
def test_currencies(client, db, customer_headers, manager, currency, base, expected_tour_uah):
    tour = make_active_tour(db, manager, days_ahead=10, base_price=Decimal(base), currency=currency)
    price = ok(quote(client, customer_headers, tour, adults=1))
    assert price["tour_uah"] == expected_tour_uah


def test_rounding_half_up(client, db, customer_headers, manager):
    set_rate(db, Currency.EUR, "41.2250")
    tour = make_active_tour(db, manager, days_ahead=10, base_price=Decimal("1.00"))
    assert ok(quote(client, customer_headers, tour, adults=1))["tour_uah"] == "41.23"  # not 41.22


def test_chosen_insurance_and_transfer(client, db, customer_headers, tour):
    price = ok(quote(client, customer_headers, tour, adults=2, children=1,
                     insurance_type_id=option_id(db, InsuranceType, "Розширене"),
                     transfer_type_id=option_id(db, TransferType, "Індивідуальний")))
    assert (price["insurance_per_tourist_uah"], price["insurance_uah"]) == ("700.00", "2100.00")
    assert price["transfer_uah"] == "2500.00"         # per order, not per tourist
    assert price["total_uah"] == "100600.00"          # 96000 + 2100 + 2500


def test_unknown_or_archived_option(client, db, customer_headers, tour):
    assert "страхування" in error(quote(client, customer_headers, tour, insurance_type_id=999999))
    vip = db.get(TransferType, option_id(db, TransferType, "VIP"))
    vip.is_archived = True
    db.flush()
    assert "трансферу" in error(quote(client, customer_headers, tour, transfer_type_id=vip.id))


def test_tourists_birth_dates_must_match_categories(client, customer_headers, tour):
    adult, child = years_before(START, 30), years_before(START, 5)
    twelve = years_before(START, 12)
    body = {"tourists": [{"birth_date": adult.isoformat()}, {"birth_date": child.isoformat()}]}
    assert ok(quote(client, customer_headers, tour, adults=1, children=1, **body))
    message = error(quote(client, customer_headers, tour, adults=2, children=0, **body))
    assert "дорослих — 1, дітей — 1" in message
    exactly_12 = {"tourists": [{"birth_date": adult.isoformat()}, {"birth_date": twelve.isoformat()}]}
    assert ok(quote(client, customer_headers, tour, adults=2, children=0, **exactly_12))
    assert "дорівнювати" in error(quote(client, customer_headers, tour, adults=3, **body))


def test_quote_writes_nothing(client, db, customer_headers, tour):
    make_promo(db, code="SAVE10")
    before = db.scalar(select(func.count()).select_from(Order))
    ok(quote(client, customer_headers, tour, promo_code="SAVE10"))
    assert db.scalar(select(func.count()).select_from(Order)) == before


# ---------- promo codes
def test_promo_percent(client, db, customer_headers, tour):
    make_promo(db, code="SUMMER10", value="10")
    price = ok(quote(client, customer_headers, tour, adults=2, children=1, promo_code="summer10 "))
    assert price["promo_code"] == "SUMMER10"
    assert price["discount_uah"] == "9705.00"         # 10 % of 97 050 (incl. insurance)
    assert price["total_uah"] == "87345.00"


def test_promo_fixed(client, db, customer_headers, tour):
    make_promo(db, code="MINUS500", discount_type=DiscountType.FIXED, value="500")
    price = ok(quote(client, customer_headers, tour, promo_code="MINUS500"))
    assert (price["discount_uah"], price["total_uah"]) == ("500.00", "77000.00")


def test_discount_cannot_exceed_subtotal(client, db, customer_headers, tour):
    make_promo(db, code="HUGE", discount_type=DiscountType.FIXED, value="200000")
    price = ok(quote(client, customer_headers, tour, promo_code="HUGE"))
    assert (price["discount_uah"], price["total_uah"]) == ("77500.00", "0.00")


def test_promo_minimum_amount(client, db, customer_headers, tour):
    make_promo(db, code="BIG", min_order="80000")
    assert error(quote(client, customer_headers, tour, adults=2, promo_code="BIG")) == \
        "Промокод діє для замовлень від 80000.00 грн"
    assert ok(quote(client, customer_headers, tour, adults=2, children=1, promo_code="BIG"))


@pytest.mark.parametrize("promo_kwargs,message", [
    ({"valid_from": date.today() - timedelta(days=30), "valid_to": date.today() - timedelta(days=1)},
     "Термін дії промокоду минув"),
    ({"valid_from": date.today() + timedelta(days=1)}, "Промокод діє з"),
    ({"is_active": False}, "Промокод неактивний"),
])
def test_promo_not_valid(client, db, customer_headers, tour, promo_kwargs, message):
    make_promo(db, code="CODE", **promo_kwargs)
    assert message in error(quote(client, customer_headers, tour, promo_code="CODE"))


def test_unknown_promo(client, customer_headers, tour):
    assert error(quote(client, customer_headers, tour, promo_code="NOPE")) == "Промокод не знайдено"


def test_promo_usage_limit(client, db, customer_headers, tour):
    promo = make_promo(db, code="ONCE", usage_limit=1)
    other = make_user(db)
    now = datetime.now(timezone.utc)
    # These do not use up the limit: cancelled, rejected, expired hold.
    for status, hold in [(OrderStatus.CANCELLED, None), (OrderStatus.REJECTED, None),
                         (OrderStatus.CHECKOUT, now - timedelta(minutes=1))]:
        make_order(db, other, tour, promo_code_id=promo.id, status=status, hold_expires_at=hold)
    assert ok(quote(client, customer_headers, tour, promo_code="ONCE"))
    # An order still holding seats does.
    make_order(db, other, tour, promo_code_id=promo.id, hold_expires_at=now + timedelta(minutes=10))
    assert error(quote(client, customer_headers, tour, promo_code="ONCE")) == \
        "Ліміт використань промокоду вичерпано"
