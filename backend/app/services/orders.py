"""Client checkout (ТЗ 4.5.3, form 4.6.1.2, seat-hold rules of 4.4.1).

Flow: create (checkout, seats held) -> update while in checkout -> confirm («Перейти до оплати»,
price frozen, awaiting_payment) or cancel. The hold lasts booking_timeout_min from creation and
is never extended. An order whose hold has run out is cancelled by the System on the next touch
(and by the background job, see services/order_expiry.py).
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (ORDER_NUMBER_SEQ, CurrencyRate, InsuranceType, Order, OrderTourist,
                        PromoCode, Tour, TransferType, User)
from app.models.enums import OrderStatus, PaymentStatus, TourStatus
from app.services import order_status
from app.services.app_settings import booking_timeout_min
from app.services.errors import DomainError
from app.services.order_expiry import HOLD_EXPIRED_COMMENT
from app.services.passports import clean_latin_name, clean_passport_number
from app.services.payments.sessions import close_open_sessions
from app.services.pricing import PriceBreakdown, calculate, is_child
from app.services.promo import find_valid_promo
from app.services.seats import HOLDING_STATUSES, free_seats, lock_tour

PASSPORT_MONTHS_AFTER_RETURN = 6      # form 4.6.1.2, field 3.5
MAX_TOURISTS = 20
MAX_WISHES = 1000


class HoldExpired(DomainError):
    """The order was just cancelled by the System because its hold ran out.
    The router commits that cancellation before returning the error."""

    def __init__(self):
        super().__init__("Час на оформлення замовлення минув — замовлення скасовано", 409)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


# ---------- checks
def _bookable_tour(db: Session, tour_id: int, lock: bool) -> Tour:
    tour = lock_tour(db, tour_id) if lock else db.get(Tour, tour_id)
    if tour is None or tour.status != TourStatus.ACTIVE:
        raise DomainError("Тур недоступний для бронювання", 422)
    return tour


def _check_start_date(tour: Tour, start_date: date) -> date:
    """Returns end_date = start_date + nights."""
    if start_date < date.today() + timedelta(days=1):
        raise DomainError("Дата заїзду — не раніше завтрашнього дня", 422)
    if not tour.departure_from <= start_date <= tour.departure_to:
        raise DomainError(f"Дата заїзду має бути в межах {tour.departure_from:%d.%m.%Y}–"
                          f"{tour.departure_to:%d.%m.%Y}", 422)
    return start_date + timedelta(days=tour.nights)


def _check_counts(adults: int, children: int) -> None:
    if adults < 1:
        raise DomainError("Потрібен щонайменше один дорослий турист", 422)
    if children < 0:
        raise DomainError("Кількість дітей не може бути від'ємною", 422)
    if adults + children > MAX_TOURISTS:
        raise DomainError(f"В одному замовленні — не більше {MAX_TOURISTS} туристів", 422)


def _check_categories(birth_dates: list[date], adults: int, children: int, start_date: date) -> None:
    """The category comes from the birth date (child = under 12 on the start date), so the
    tourists must match the chosen numbers of adults and children."""
    if len(birth_dates) != adults + children:
        raise DomainError(f"Кількість туристів ({len(birth_dates)}) має дорівнювати кількості "
                          f"дорослих і дітей ({adults + children})", 422)
    for birth_date in birth_dates:
        if birth_date > start_date:
            raise DomainError("Дата народження не може бути пізніше дати заїзду", 422)
    real_children = sum(is_child(b, start_date) for b in birth_dates)
    if real_children != children:
        raise DomainError(f"За датами народження: дорослих — {len(birth_dates) - real_children}, "
                          f"дітей — {real_children} (дитина — до 12 років на дату заїзду), "
                          f"а обрано дорослих — {adults}, дітей — {children}", 422)


def _clean_tourist(data: dict[str, Any], end_date: date) -> dict[str, Any]:
    """Form 4.6.1.2, fields 3.2–3.5: Latin names, passport number, validity after the return."""
    name = f"{data['last_name_lat']} {data['first_name_lat']}".strip()
    data["last_name_lat"] = clean_latin_name(data["last_name_lat"])
    data["first_name_lat"] = clean_latin_name(data["first_name_lat"])
    data["passport_number"] = clean_passport_number(data["passport_number"])
    must_be_valid_until = add_months(end_date, PASSPORT_MONTHS_AFTER_RETURN)
    if data["passport_expiry"] < must_be_valid_until:
        raise DomainError(f"Паспорт туриста {name} має діяти щонайменше 6 місяців після "
                          f"повернення — до {must_be_valid_until:%d.%m.%Y}", 422)
    return data


def _check_wishes(wishes: str | None) -> str | None:
    if wishes is not None and len(wishes) > MAX_WISHES:
        raise DomainError(f"Побажання — не довше {MAX_WISHES} символів", 422)
    if wishes is None:
        return None
    return wishes.strip() or None


def _insurance(db: Session, insurance_id: int | None) -> InsuranceType | None:
    if insurance_id is None:   # form 4.6.1.2, field 4: «Базове» by default
        return db.scalar(select(InsuranceType).where(InsuranceType.is_default.is_(True),
                                                     InsuranceType.is_archived.is_(False)))
    insurance = db.get(InsuranceType, insurance_id)
    if insurance is None or insurance.is_archived:
        raise DomainError("Тип страхування не знайдено", 422)
    return insurance


def _transfer(db: Session, transfer_id: int | None) -> TransferType | None:
    if transfer_id is None:    # form 4.6.1.2, field 5: «Груповий» by default
        return db.scalar(select(TransferType).where(TransferType.is_default.is_(True),
                                                    TransferType.is_archived.is_(False)))
    transfer = db.get(TransferType, transfer_id)
    if transfer is None or transfer.is_archived:
        raise DomainError("Тип трансферу не знайдено", 422)
    return transfer


def _rate(db: Session, tour: Tour):
    rate = db.get(CurrencyRate, tour.currency)
    if rate is None:
        raise DomainError("Курс валюти туру не встановлено — зверніться до адміністратора", 422)
    return rate.rate_to_uah


def _price(db: Session, tour: Tour, adults: int, children: int, insurance, transfer,
           promo_code: str | None, *, exclude_order_id: int | None = None,
           lock_promo: bool = False) -> tuple[PriceBreakdown, PromoCode | None]:
    rate = _rate(db, tour)
    price = calculate(tour, rate, adults, children, insurance, transfer)
    if not promo_code:
        return price, None
    promo = find_valid_promo(db, promo_code, price.subtotal_uah, date.today(),
                             exclude_order_id=exclude_order_id, lock=lock_promo)
    return calculate(tour, rate, adults, children, insurance, transfer, promo), promo


# ---------- quote
def quote(db: Session, data: dict[str, Any]) -> PriceBreakdown:
    """Price preview: same checks as the order, writes nothing."""
    tour = _bookable_tour(db, data["tour_id"], lock=False)
    _check_start_date(tour, data["start_date"])
    _check_counts(data["adults"], data["children"])
    if data.get("tourists") is not None:
        _check_categories([t["birth_date"] for t in data["tourists"]], data["adults"],
                          data["children"], data["start_date"])
    price, _ = _price(db, tour, data["adults"], data["children"],
                      _insurance(db, data.get("insurance_type_id")),
                      _transfer(db, data.get("transfer_type_id")), data.get("promo_code"))
    return price


# ---------- orders of one client
def get_own_order(db: Session, client: User, order_id: int) -> Order:
    """Someone else's order looks exactly like a missing one (404), so ids cannot be probed."""
    order = db.scalar(select(Order).where(Order.id == order_id, Order.client_id == client.id)
                      .options(selectinload(Order.tourists), selectinload(Order.history)))
    if order is None:
        raise DomainError("Замовлення не знайдено", 404)
    return order


def list_own_orders(db: Session, client: User, status: OrderStatus | None, page: int,
                    page_size: int) -> tuple[list[Order], int]:
    query = select(Order).where(Order.client_id == client.id)
    if status is not None:
        query = query.where(Order.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def expire_if_due(db: Session, order: Order, now: datetime | None = None) -> bool:
    """Cancel the order as the System if its hold has run out. True if it was cancelled.
    A partly paid order (bank transfer) is never cancelled automatically: money has arrived."""
    now = now or utcnow()
    if order.status in HOLDING_STATUSES and order.hold_expires_at is not None \
            and order.hold_expires_at <= now and order.payment_status != PaymentStatus.PARTIALLY_PAID:
        close_open_sessions(db, order)   # the client must not be able to pay any more
        order_status.change_status(db, order, OrderStatus.CANCELLED, None, HOLD_EXPIRED_COMMENT)
        return True
    return False


def _next_number(db: Session) -> str:
    return f"TU-{date.today().year}-{db.scalar(ORDER_NUMBER_SEQ.next_value()):06d}"


def create_order(db: Session, client: User, data: dict[str, Any]) -> tuple[Order, PriceBreakdown]:
    """«Забронювати» (ТЗ 4.5.3 step 2): number, status «Оформлення», seats held."""
    adults, children = data["adults"], data["children"]
    _check_counts(adults, children)
    tour = _bookable_tour(db, data["tour_id"], lock=True)   # serialises bookings of this tour
    end_date = _check_start_date(tour, data["start_date"])
    tourists = data.get("tourists")
    if tourists is not None:
        _check_categories([t["birth_date"] for t in tourists], adults, children, data["start_date"])
        tourists = [_clean_tourist(t, end_date) for t in tourists]

    now = utcnow()
    available = free_seats(db, tour.id, now)
    if available < adults + children:
        raise DomainError(f"Недостатньо вільних місць: залишилось {max(available, 0)}", 409)

    insurance = _insurance(db, data.get("insurance_type_id"))
    transfer = _transfer(db, data.get("transfer_type_id"))
    price, promo = _price(db, tour, adults, children, insurance, transfer, data.get("promo_code"),
                          lock_promo=True)
    order = Order(
        number=_next_number(db), client_id=client.id, tour_id=tour.id,
        status=OrderStatus.CHECKOUT, start_date=data["start_date"], end_date=end_date,
        adults=adults, children=children,
        insurance_type_id=insurance.id if insurance else None,
        transfer_type_id=transfer.id if transfer else None,
        promo_code_id=promo.id if promo else None, wishes=_check_wishes(data.get("wishes")),
        total_uah=price.total_uah, discount_uah=price.discount_uah, rate_used=price.rate,
        hold_expires_at=now + timedelta(minutes=booking_timeout_min(db)),
    )
    order.tourists = [OrderTourist(**t) for t in tourists or []]
    db.add(order)
    db.flush()
    order_status.record_created(db, order, client)
    return order, price


def _ensure_editable(db: Session, order: Order) -> None:
    if expire_if_due(db, order):
        raise HoldExpired()
    if order.status != OrderStatus.CHECKOUT:
        raise DomainError("Змінювати можна лише замовлення в статусі «Оформлення»", 409)


def update_order(db: Session, order: Order, changes: dict[str, Any]) -> tuple[Order, PriceBreakdown]:
    """Edit while in checkout; the price is recalculated, the hold timer is NOT extended."""
    _ensure_editable(db, order)
    tour = lock_tour(db, order.tour_id)
    adults = changes.get("adults") if changes.get("adults") is not None else order.adults
    children = changes.get("children") if changes.get("children") is not None else order.children
    _check_counts(adults, children)

    if changes.get("tourists") is not None:
        tourists = changes["tourists"]
        _check_categories([t["birth_date"] for t in tourists], adults, children, order.start_date)
        tourists = [_clean_tourist(t, order.end_date) for t in tourists]
    else:
        tourists = None
        if order.tourists:   # the stored list must still match the (possibly new) numbers
            _check_categories([t.birth_date for t in order.tourists], adults, children,
                              order.start_date)

    if adults + children > order.adults + order.children:   # more seats: check under the lock
        available = free_seats(db, tour.id, utcnow(), exclude_order_id=order.id)
        if available < adults + children:
            raise DomainError(f"Недостатньо вільних місць: можна не більше {max(available, 0)} "
                              f"туристів", 409)

    insurance = (_insurance(db, changes["insurance_type_id"]) if "insurance_type_id" in changes
                 else order.insurance_type)
    transfer = (_transfer(db, changes["transfer_type_id"]) if "transfer_type_id" in changes
                else order.transfer_type)
    promo_code = changes["promo_code"] if "promo_code" in changes else (
        order.promo.code if order.promo else None)
    price, promo = _price(db, tour, adults, children, insurance, transfer, promo_code,
                          exclude_order_id=order.id, lock_promo=True)

    order.adults, order.children = adults, children
    if tourists is not None:
        order.tourists = [OrderTourist(**t) for t in tourists]
    order.insurance_type = insurance
    order.transfer_type = transfer
    order.promo = promo
    if "wishes" in changes:
        order.wishes = _check_wishes(changes["wishes"])
    order.total_uah, order.discount_uah, order.rate_used = price.total_uah, price.discount_uah, price.rate
    db.flush()
    return order, price


def confirm_order(db: Session, client: User, order: Order,
                  accept_offer: bool) -> tuple[Order, PriceBreakdown]:
    """«Перейти до оплати» (ТЗ 4.5.3 step 7.2): full validation, the price is recalculated with
    today's rate and promo, then frozen; status -> «Очікує оплати»."""
    _ensure_editable(db, order)
    if not accept_offer:
        raise DomainError("Потрібна згода з Договором публічної оферти", 422)
    tour = _bookable_tour(db, order.tour_id, lock=True)
    if len(order.tourists) != order.adults + order.children:
        raise DomainError(f"Внесіть дані всіх туристів: потрібно {order.adults + order.children}, "
                          f"внесено {len(order.tourists)}", 422)
    _check_categories([t.birth_date for t in order.tourists], order.adults, order.children,
                      order.start_date)
    for tourist in order.tourists:   # passports may have been entered for other dates
        _clean_tourist({"last_name_lat": tourist.last_name_lat,
                        "first_name_lat": tourist.first_name_lat,
                        "passport_number": tourist.passport_number,
                        "passport_expiry": tourist.passport_expiry}, order.end_date)

    price, promo = _price(db, tour, order.adults, order.children, order.insurance_type,
                          order.transfer_type, order.promo.code if order.promo else None,
                          exclude_order_id=order.id, lock_promo=True)
    # Frozen from here on: later changes of rates or service prices do not touch this order.
    order.total_uah, order.discount_uah, order.rate_used = price.total_uah, price.discount_uah, price.rate
    order.promo = promo
    order.offer_accepted_at = utcnow()
    order_status.change_status(db, order, OrderStatus.AWAITING_PAYMENT, client)
    return order, price


def cancel_order(db: Session, client: User, order: Order) -> Order:
    """ТЗ 4.5.3 step 7.1: cancel before payment; the hold stops counting at once.
    A paid order is cancelled through a cancellation request (feature/order-processing)."""
    if expire_if_due(db, order):
        return order   # already cancelled by the System — the client's wish is fulfilled
    if order.status not in HOLDING_STATUSES:
        raise DomainError("Скасувати тут можна лише неоплачене замовлення", 409)
    if order.payment_status == PaymentStatus.PARTIALLY_PAID:
        raise DomainError("Замовлення частково оплачене — для скасування зверніться до менеджера", 409)
    close_open_sessions(db, order)
    order_status.change_status(db, order, OrderStatus.CANCELLED, client, "Скасовано клієнтом")
    return order
