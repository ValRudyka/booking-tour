"""Manager's tour management (ТЗ 4.5.2, form 4.6.2.1) and tour statuses (ТЗ 4.4.1).

Rules that need the whole tour (date order, program length vs. nights, flight numbers only for
air) are checked here on the merged values, so a PATCH of one field cannot break the tour.

Bookings that depend on a tour (spec 10):
- the facts in LOCKED_FIELDS cannot change while an order's page reads them from the tour row
  (an order that was ever paid) or a client is paying for them (an active booking);
- unpublish leaves bookings payable; archive cancels the unpaid ones.
"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, BinaryIO

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (AuditLog, City, Country, Hotel, Order, OrderStatusHistory, Resort, Tour,
                        TourImage, TourProgramDay, User)
from app.models.enums import ManagerTourSort, OrderStatus, PaymentStatus, TourStatus, TransportType
from app.services import clock, order_status
from app.services import images as image_files
from app.services.catalog import UKRAINIAN_COLLATION
from app.services.errors import DomainError
from app.services.payments.sessions import close_open_sessions
from app.services.seats import HOLDING_STATUSES, held_seats, lock_tour
from app.services.text_lists import clean_text_list

STATUS_LABELS = {TourStatus.DRAFT: "Чернетка", TourStatus.ACTIVE: "Активний",
                 TourStatus.ARCHIVED: "Архівний"}

# ТЗ 4.4.1: draft -> active (publish), active -> draft (back to editing), both -> archived.
# Spec 10 adds «Відновити»: archived -> draft (publishing again needs a valid start date).
ALLOWED_TRANSITIONS: dict[TourStatus, set[TourStatus]] = {
    TourStatus.DRAFT: {TourStatus.ACTIVE, TourStatus.ARCHIVED},
    TourStatus.ACTIVE: {TourStatus.DRAFT, TourStatus.ARCHIVED},
    TourStatus.ARCHIVED: {TourStatus.DRAFT},
}

# Editable columns of form 4.6.2.1 (everything except status, quota usage and authorship).
TOUR_FIELDS = ("title_uk", "title_en", "hotel_id", "transport_type", "departure_city_id",
               "flight_out", "flight_back", "departure_from", "departure_to", "nights",
               "seats_total", "base_price", "child_price", "currency", "description", "is_featured",
               "meal_plan", "included", "excluded")
REQUIRED_LABELS = {"title_en": "назва туру англійською", "hotel_id": "готель",
                   "transport_type": "тип транспорту", "departure_from": "дата заїзду «від»",
                   "departure_to": "дата заїзду «до»", "nights": "тривалість (ночей)",
                   "seats_total": "жорсткий блок місць", "base_price": "базова вартість",
                   "currency": "валюта туру", "is_featured": "рекомендований тур"}

# Facts the client's order pages read live from the tour row (routers/order_views.py) until
# feature/order-snapshot stores them in the order. Locked while an order depends on them
# (lock_reason). Prices are not here: an order freezes its own price at confirm.
LOCKED_FIELDS = ("title_uk", "title_en", "hotel_id", "departure_from", "departure_to", "nights",
                 "transport_type", "departure_city_id", "meal_plan")
ARCHIVE_CANCEL_COMMENT = "Тур знято з продажу"

FLIGHT_RE = re.compile(r"^[A-Z0-9]{2} ?\d{1,4}[A-Z]?$")   # e.g. QU 4433, PS101
MAX_TITLE = 200
MAX_DESCRIPTION = 5000                                    # form 4.6.2.1, field 16
MAX_DAY_TEXT = 2000
MIN_NIGHTS, MAX_NIGHTS = 1, 30                            # form 4.6.2.1, field 11
MAX_MONEY = Decimal("9999999999.99")                      # fits Numeric(12, 2)



def _error(message: str, status_code: int = 422, field: str | None = None) -> DomainError:
    """`field` names the form field the rule is about: the router then answers in FastAPI's 422
    shape with that `loc`, so the editor shows the message under the field (spec 03 §2a)."""
    return DomainError(message, status_code, loc=("body", field) if field else None)


# ---------- reading
def get_tour(db: Session, tour_id: int) -> Tour:
    tour = db.scalar(select(Tour).where(Tour.id == tour_id)
                     .options(selectinload(Tour.program_days), selectinload(Tour.images)))
    if tour is None:
        raise _error("Тур не знайдено", 404)
    return tour


SORTS = {
    ManagerTourSort.UPDATED_DESC: (Tour.updated_at.desc(), Tour.id.desc()),
    ManagerTourSort.DEPARTURE_ASC: (Tour.departure_from.asc(), Tour.id.asc()),
    ManagerTourSort.TITLE_ASC: (Tour.title_uk.collate(UKRAINIAN_COLLATION).asc(), Tour.id.asc()),
}


def list_tours(db: Session, *, status: TourStatus | None, q: str | None,
               country_id: int | None = None, resort_id: int | None = None,
               departure_from: date | None = None, departure_to: date | None = None,
               sort: ManagerTourSort = ManagerTourSort.UPDATED_DESC, page: int = 1,
               page_size: int = 20) -> tuple[list[Tour], int]:
    """Back-office list: all tours of all managers. The departure period keeps the tours whose
    date range overlaps it."""
    query = (select(Tour).join(Hotel, Tour.hotel_id == Hotel.id)
             .join(Resort, Hotel.resort_id == Resort.id))
    if status is not None:
        query = query.where(Tour.status == status)
    if q:
        query = query.where(or_(Tour.title_uk.icontains(q, autoescape=True),
                                Tour.title_en.icontains(q, autoescape=True)))
    if country_id is not None:
        query = query.where(Resort.country_id == country_id)
    if resort_id is not None:
        query = query.where(Hotel.resort_id == resort_id)
    if departure_from is not None:
        query = query.where(Tour.departure_to >= departure_from)
    if departure_to is not None:
        query = query.where(Tour.departure_from <= departure_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(selectinload(Tour.images))
                       .order_by(*SORTS[sort]).offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def nearest_start(tour: Tour) -> date | None:
    """The first start date a client could still book (from tomorrow), or None when all passed."""
    first = max(tour.departure_from, clock.tomorrow())
    return first if first <= tour.departure_to else None


# ---------- bookings that depend on the tour
def booking_counts(db: Session, tour_id: int, now: datetime | None = None) -> dict[str, int]:
    """One query for everything the actions and locks need:
    - `paid_orders`: orders that ever reached `paid` (history) — refunded or archived ones too,
      their pages still read the live tour;
    - `active_bookings`: checkout / awaiting_payment with an unexpired hold, or a partly paid
      transfer (never cancelled automatically, whatever its hold);
    - `partly_paid`: of those, the partly paid transfers (archive refuses them);
    - `archive_cancels`: the unpaid bookings archive would cancel (holding, not partly paid)."""
    now = now or clock.now()
    holding = Order.status.in_(HOLDING_STATUSES)
    partly = Order.payment_status == PaymentStatus.PARTIALLY_PAID
    ever_paid = Order.id.in_(select(OrderStatusHistory.order_id)
                             .where(OrderStatusHistory.new_status == OrderStatus.PAID.value))
    row = db.execute(select(
        func.count().filter(ever_paid),
        func.count().filter(holding, or_(Order.hold_expires_at > now, partly)),
        func.count().filter(holding, partly),
        func.count().filter(holding, ~partly),
    ).where(Order.tour_id == tour_id)).one()
    return dict(paid_orders=row[0], active_bookings=row[1], partly_paid=row[2],
                archive_cancels=row[3])


def lock_reason(counts: dict[str, int]) -> str | None:
    """Why LOCKED_FIELDS cannot change now, or None. The active-bookings lock ends by itself
    when the holds are paid (then the paid-order lock takes over) or run out."""
    if counts["paid_orders"]:
        return ("На тур уже є оплачені замовлення: їхні сторінки показують ці дані з туру. "
                "Для інших умов створіть копію туру.")
    if counts["active_bookings"]:
        return (f"{counts['active_bookings']} активних бронювань: дочекайтеся оплати або "
                f"закінчення утримання")
    return None


def locked_fields(counts: dict[str, int]) -> list[dict[str, str]]:
    reason = lock_reason(counts)
    return [dict(field=field, reason=reason) for field in LOCKED_FIELDS] if reason else []


def seats_held(db: Session, tour_id: int, now: datetime | None = None) -> int:
    """Seats in unexpired holds of this tour (the same subquery as the free-seat count)."""
    return db.scalar(select(held_seats(now or clock.now())).select_from(Tour)
                     .where(Tour.id == tour_id)) or 0


# ---------- validation
def _check_hotel(db: Session, hotel_id: int, keep_archived: bool = False) -> Hotel:
    """`keep_archived`: the tour already has this hotel (an edit that does not change it), so
    an archived one is kept; publishing checks it again without this exception."""
    hotel = db.get(Hotel, hotel_id)
    if hotel is None:
        raise _error("Готель не знайдено", field="hotel_id")
    if keep_archived:
        return hotel
    if hotel.is_archived or hotel.resort.is_archived or hotel.resort.country.is_archived:
        raise _error("Готель, курорт або країна в архіві — оберіть інший готель", field="hotel_id")
    return hotel


def _check_city(db: Session, city_id: int, keep_archived: bool = False) -> None:
    city = db.get(City, city_id)
    if city is not None and keep_archived:
        return
    if city is None:
        raise _error("Місто відправлення не знайдено", field="departure_city_id")
    # The reason, so the manager knows what to do (spec 13: publishing names the archived record).
    if city.is_archived or db.get(Country, city.country_id).is_archived:
        raise _error("Місто відправлення або його країна в архіві — оберіть інше місто", field="departure_city_id")


def _normalize_flight(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    value = " ".join(value.upper().split())
    if not value:
        return None
    if not FLIGHT_RE.match(value):
        raise _error("Номер рейсу має формат на кшталт QU 4433", field=field)
    return value


def _clean_list(values, label: str, field: str) -> list[str]:
    try:
        return clean_text_list(values, label)
    except DomainError as error:
        raise _error(error.message, field=field) from None


def _check_fields(db: Session, d: dict[str, Any], seats_sold: int, seats_held_now: int = 0,
                  current: Tour | None = None) -> dict[str, Any]:
    """Validate and normalise all editable fields of a tour. Returns the cleaned values.
    The quota may not drop below the seats sold plus the seats in unexpired holds: otherwise a
    client in the middle of paying would lose the seat at `paid` (and get an automatic refund).
    `current` (an edit): the tour's own hotel and departure city stay acceptable even if the
    admin archived them since, so a draft can still be saved (e.g. its prices, or while its
    hotel is locked); publishing re-checks them without `current`."""
    for field, label in REQUIRED_LABELS.items():
        if d.get(field) is None:
            raise _error(f"Заповніть обов'язкове поле: {label}", field=field)

    d["title_en"] = d["title_en"].strip()
    if not d["title_en"]:
        raise _error("Заповніть обов'язкове поле: назва туру англійською", field="title_en")
    hotel = _check_hotel(db, d["hotel_id"],
                         keep_archived=current is not None and d["hotel_id"] == current.hotel_id)
    # Form 4.6.2.1, field 1: the Ukrainian title is generated as "Hotel + Resort" when left empty.
    d["title_uk"] = (d.get("title_uk") or "").strip() or f"{hotel.name}, {hotel.resort.name_uk}"
    for field in ("title_uk", "title_en"):
        if len(d[field]) > MAX_TITLE:
            raise _error(f"Назва туру — не довше {MAX_TITLE} символів", field=field)

    transport = d["transport_type"]
    if transport in (TransportType.AIR, TransportType.BUS) and d.get("departure_city_id") is None:
        raise _error("Для авіа та автобуса вкажіть місто відправлення", field="departure_city_id")
    if d.get("departure_city_id") is not None:
        _check_city(db, d["departure_city_id"], keep_archived=current is not None
                    and d["departure_city_id"] == current.departure_city_id)
    d["flight_out"] = _normalize_flight(d.get("flight_out"), "flight_out")
    d["flight_back"] = _normalize_flight(d.get("flight_back"), "flight_back")
    if transport != TransportType.AIR and (d["flight_out"] or d["flight_back"]):
        raise _error("Номери рейсів вказуються лише для авіаперельоту",
                     field="flight_out" if d["flight_out"] else "flight_back")

    if d["departure_to"] < d["departure_from"]:
        raise _error("Дата заїзду «до» не може бути раніше дати «від»", field="departure_to")
    if not MIN_NIGHTS <= d["nights"] <= MAX_NIGHTS:
        raise _error(f"Тривалість туру — від {MIN_NIGHTS} до {MAX_NIGHTS} ночей", field="nights")
    if d["seats_total"] < 1:
        raise _error("Жорсткий блок місць — не менше 1", field="seats_total")
    if d["seats_total"] < seats_sold + seats_held_now:
        if seats_held_now:
            message = (f"Квота не може бути меншою за {seats_sold + seats_held_now}: продано "
                       f"{seats_sold}, утримано в активних бронюваннях {seats_held_now}")
        else:
            message = f"Квота не може бути меншою за вже продані місця ({seats_sold})"
        raise _error(message, field="seats_total")
    if not Decimal(0) < d["base_price"] <= MAX_MONEY:
        raise _error("Базова вартість має бути більшою за 0", field="base_price")
    if d.get("child_price") is not None and not Decimal(0) <= d["child_price"] <= MAX_MONEY:
        raise _error("Ціна для дитини не може бути від'ємною", field="child_price")
    if d.get("description") is not None and len(d["description"]) > MAX_DESCRIPTION:
        raise _error(f"Опис туру — не довше {MAX_DESCRIPTION} символів", field="description")
    d["included"] = _clean_list(d.get("included"), "Що включено", "included")
    d["excluded"] = _clean_list(d.get("excluded"), "Що не включено", "excluded")
    return d


def _check_program(days: list[dict[str, Any]], nights: int) -> list[tuple[int, str]]:
    """Form 4.6.2.1, field 17: days are numbered 1, 2, 3... without gaps; a tour of N nights
    has at most N + 1 days."""
    numbers = sorted(day["day_number"] for day in days)
    if numbers != list(range(1, len(days) + 1)):
        raise _error("Дні програми мають іти по порядку без пропусків і повторів: 1, 2, 3…",
                     field="program_days")
    if len(days) > nights + 1:
        raise _error(f"Програма не може бути довшою за тур: максимум {nights + 1} дн.",
                     field="program_days")
    result = []
    for index, day in enumerate(sorted(days, key=lambda item: item["day_number"])):
        text = (day["description"] or "").strip()
        # loc names the day by its position (= day_number - 1), as the editor's Form.List does.
        loc = ("body", "program_days", index, "description")
        if not text:
            raise DomainError("Опишіть маршрут для кожного дня програми", 422, loc=loc)
        if len(text) > MAX_DAY_TEXT:
            raise DomainError(f"Опис дня програми — не довше {MAX_DAY_TEXT} символів", 422, loc=loc)
        result.append((day["day_number"], text))
    return result


def edit_refusal(tour: Tour) -> str | None:
    """ТЗ 4.4.1: an active tour goes back to «Чернетка» for editing."""
    if tour.status == TourStatus.ARCHIVED:
        return "Архівний тур змінювати не можна — відновіть його або створіть копію"
    if tour.status != TourStatus.DRAFT:
        return "Редагувати можна лише чернетку — спершу зніміть тур з публікації"
    return None


def _ensure_draft(tour: Tour) -> None:
    reason = edit_refusal(tour)
    if reason:
        raise _error(reason, 409)


def _current_program(tour: Tour) -> list[dict[str, Any]]:
    return [{"day_number": d.day_number, "description": d.description} for d in tour.program_days]


# ---------- changes
def create_tour(db: Session, data: dict[str, Any], manager: User) -> Tour:
    """Scenario 4.5.2, option 4.2 «Зберегти чернетку»: a new tour is always a draft."""
    days = data.pop("program_days", None) or []
    fields = _check_fields(db, data, seats_sold=0)
    program = _check_program(days, fields["nights"])
    tour = Tour(**fields, created_by=manager.id, status=TourStatus.DRAFT)
    tour.program_days = [TourProgramDay(day_number=n, description=text) for n, text in program]
    db.add(tour)
    db.flush()
    return tour


def update_tour(db: Session, tour: Tour, changes: dict[str, Any]) -> Tour:
    _ensure_draft(tour)
    # Lock the row: bookings and payments change seats_sold and holds under the same lock.
    tour = lock_tour(db, tour.id)
    days = changes.pop("program_days", None)
    merged = {field: getattr(tour, field) for field in TOUR_FIELDS} | changes
    fields = _check_fields(db, merged, tour.seats_sold, seats_held(db, tour.id), current=tour)
    # Locked facts may be sent unchanged (the editor PATCHes the whole form), never changed.
    reason = lock_reason(booking_counts(db, tour.id))
    if reason:
        for field in LOCKED_FIELDS:
            if fields[field] != getattr(tour, field):
                raise _error(reason, 409, field=field)
    # Re-check the existing program too: fewer nights may make it too long.
    program = _check_program(days if days is not None else _current_program(tour), fields["nights"])
    for field, value in fields.items():
        setattr(tour, field, value)
    if days is not None:
        tour.program_days = [TourProgramDay(day_number=n, description=text) for n, text in program]
    db.flush()
    return tour


def change_status(db: Session, tour: Tour, new_status: TourStatus, user: User,
                  from_status: TourStatus | None = None) -> Tour:
    """The only place where a tour status changes; every change goes to audit_log (ТЗ 4.4.1).

    Unpublish (-> draft) leaves the bookings alone: they stay payable, and lock_reason() keeps
    what the clients pay for unchanged until their holds are paid or run out.
    Archive cancels the unpaid bookings (_cancel_bookings) and lists them in the audit entry.
    `from_status` tells unpublish (active -> draft) from restore (archived -> draft)."""
    # Serialise with bookings and payments of this tour (they take the same row lock).
    tour = lock_tour(db, tour.id)
    old_status = tour.status
    if new_status not in ALLOWED_TRANSITIONS[old_status] or from_status not in (None, old_status):
        raise _error(f"Неможливо змінити статус туру з «{STATUS_LABELS[old_status]}» "
                     f"на «{STATUS_LABELS[new_status]}»", 409)
    if new_status == TourStatus.ACTIVE:
        _validate_for_publish(db, tour)
    new_value: dict[str, Any] = {"status": new_status.value}
    if new_status == TourStatus.ARCHIVED:
        reason = archive_refusal(booking_counts(db, tour.id))
        if reason:
            raise _error(reason, 409)
        cancelled = _cancel_bookings(db, tour, user)
        if cancelled:
            new_value["cancelled_orders"] = cancelled
    tour.status = new_status
    db.add(AuditLog(user_id=user.id, entity="tour", entity_id=str(tour.id), action="status_change",
                    old_value={"status": old_status.value}, new_value=new_value))
    db.flush()
    return tour


def archive_refusal(counts: dict[str, int]) -> str | None:
    """Money has arrived for a partly paid transfer: finance completes or refunds it; the tour
    never cancels it (the same rule as the expiry job)."""
    if counts["partly_paid"]:
        return (f"{counts['partly_paid']} бронювань частково оплачено переказом — спершу "
                f"фінансовий контролер має завершити оплату або повернути кошти")
    return None


def _cancel_bookings(db: Session, tour: Tour, user: User) -> list[str]:
    """Archive = the tour leaves sale for good: its unpaid bookings are cancelled the way the
    expiry job cancels them (open Stripe sessions closed, the client notified by change_status).
    A card payment that still arrives is refunded by the webhook, because the order is no
    longer awaiting_payment. Returns the order numbers for the audit entry."""
    from app.services.payments.service import lock_order   # payments imports orders

    order_ids = db.scalars(select(Order.id).where(
        Order.tour_id == tour.id, Order.status.in_(HOLDING_STATUSES),
        Order.payment_status != PaymentStatus.PARTIALLY_PAID).order_by(Order.id)).all()
    numbers = []
    for order_id in order_ids:
        order = lock_order(db, order_id)
        if order.status not in HOLDING_STATUSES:     # paid or cancelled meanwhile
            continue
        close_open_sessions(db, order)
        order_status.change_status(db, order, OrderStatus.CANCELLED, user, ARCHIVE_CANCEL_COMMENT)
        numbers.append(order.number)
    return numbers


def _validate_for_publish(db: Session, tour: Tour) -> None:
    """Scenario 4.5.2, option 4.3 «Опублікувати»: full validation before the tour goes public.
    Re-runs the form checks because the hotel or city may have been archived since saving."""
    _check_fields(db, {field: getattr(tour, field) for field in TOUR_FIELDS}, tour.seats_sold)
    _check_program(_current_program(tour), tour.nights)
    # Sellable while a start date from tomorrow remains (the same rule as the catalog).
    if tour.departure_to < clock.tomorrow():
        raise _error("Усі дати заїздів уже минули — оновіть дати перед публікацією",
                     field="departure_to")


def publish_refusal(db: Session, tour: Tour) -> str | None:
    """The first reason publishing would be refused (tour_actions), or None."""
    try:
        _validate_for_publish(db, tour)
    except DomainError as error:
        return error.message
    return None


COPY_PREFIX_UK = "Копія — "
COPY_PREFIX_EN = "Copy — "


def copy_tour(db: Session, source: Tour, manager: User, departure_from: date,
              departure_to: date) -> Tour:
    """New draft with the same content and new dates. Spec 10: the old dates are never copied
    (and the columns are NOT NULL, so the dialog asks for the new range first). Nothing is sold
    yet; «Рекомендований» is off. Photos are copied as files."""
    if departure_from < clock.tomorrow():
        raise _error("Дата заїзду «від» — не раніше завтрашнього дня", field="departure_from")
    if departure_to < departure_from:
        raise _error("Дата заїзду «до» не може бути раніше дати «від»", field="departure_to")
    fields = {field: getattr(source, field) for field in TOUR_FIELDS}
    fields["title_uk"] = (COPY_PREFIX_UK + source.title_uk)[:MAX_TITLE]
    fields["title_en"] = (COPY_PREFIX_EN + source.title_en)[:MAX_TITLE]
    fields.update(departure_from=departure_from, departure_to=departure_to, is_featured=False)
    tour = Tour(**fields, created_by=manager.id, status=TourStatus.DRAFT, seats_sold=0)
    tour.program_days = [TourProgramDay(day_number=d.day_number, description=d.description)
                         for d in source.program_days]
    db.add(tour)
    db.flush()  # the new id is needed for the photo folder
    for image in source.images:
        try:
            path = image_files.copy_tour_image(image.file_path, tour.id)
        except FileNotFoundError:  # file removed from disk by hand — skip it, keep the copy usable
            continue
        tour.images.append(TourImage(file_path=path, sort_order=image.sort_order))
    db.flush()
    return tour


# ---------- photos
def add_images(db: Session, tour: Tour, files: list[tuple[BinaryIO, str | None]]) -> list[TourImage]:
    """All-or-nothing: every file is checked and written first, only then rows are added."""
    _ensure_draft(tour)
    if not files:
        raise _error("Додайте хоча б один файл")
    if len(tour.images) + len(files) > settings.max_images_per_tour:
        raise _error(f"У турі може бути не більше {settings.max_images_per_tour} фото")
    saved: list[str] = []
    try:
        for stream, filename in files:
            saved.append(image_files.save_tour_image(tour.id, stream, filename))
    except BaseException:
        image_files.remove_files(saved)
        raise
    next_order = max((image.sort_order for image in tour.images), default=-1) + 1
    new_images = [TourImage(file_path=path, sort_order=next_order + i) for i, path in enumerate(saved)]
    tour.images.extend(new_images)
    db.flush()
    return new_images


def delete_image(db: Session, tour: Tour, image_id: int) -> str:
    """Removes the row and returns the file path; the router deletes the file after commit,
    so a failed transaction never leaves a row pointing to a missing file."""
    _ensure_draft(tour)
    image = next((image for image in tour.images if image.id == image_id), None)
    if image is None:
        raise _error("Фото не знайдено", 404)
    tour.images.remove(image)  # delete-orphan cascade deletes the row
    db.flush()
    return image.file_path


def reorder_images(db: Session, tour: Tour, image_ids: list[int]) -> Tour:
    """The first photo is the main one (catalog card, gallery start)."""
    _ensure_draft(tour)
    if sorted(image_ids) != sorted(image.id for image in tour.images):
        raise _error("Передайте всі фото туру, кожне по одному разу")
    position = {image_id: i for i, image_id in enumerate(image_ids)}
    for image in tour.images:
        image.sort_order = position[image.id]
    db.flush()
    db.refresh(tour, ["images"])  # re-read in the new order
    return tour
