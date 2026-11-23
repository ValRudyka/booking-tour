"""Manager's tour management (ТЗ 4.5.2, form 4.6.2.1) and tour statuses (ТЗ 4.4.1).

Rules that need the whole tour (date order, program length vs. nights, flight numbers only for
air) are checked here on the merged values, so a PATCH of one field cannot break the tour.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Any, BinaryIO

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import AuditLog, City, Hotel, Tour, TourImage, TourProgramDay, User
from app.models.enums import TourStatus, TransportType
from app.services import images as image_files
from app.services.errors import DomainError

STATUS_LABELS = {TourStatus.DRAFT: "Чернетка", TourStatus.ACTIVE: "Активний",
                 TourStatus.ARCHIVED: "Архівний"}

# ТЗ 4.4.1: draft -> active (publish), active -> draft (back to editing), both -> archived.
# Archived is final: an old tour is re-used by copying it.
ALLOWED_TRANSITIONS: dict[TourStatus, set[TourStatus]] = {
    TourStatus.DRAFT: {TourStatus.ACTIVE, TourStatus.ARCHIVED},
    TourStatus.ACTIVE: {TourStatus.DRAFT, TourStatus.ARCHIVED},
    TourStatus.ARCHIVED: set(),
}

# Editable columns of form 4.6.2.1 (everything except status, quota usage and authorship).
TOUR_FIELDS = ("title_uk", "title_en", "hotel_id", "transport_type", "departure_city_id",
               "flight_out", "flight_back", "departure_from", "departure_to", "nights",
               "seats_total", "base_price", "child_price", "currency", "description", "is_featured")
REQUIRED_LABELS = {"title_en": "назва туру англійською", "hotel_id": "готель",
                   "transport_type": "тип транспорту", "departure_from": "дата заїзду «від»",
                   "departure_to": "дата заїзду «до»", "nights": "тривалість (ночей)",
                   "seats_total": "жорсткий блок місць", "base_price": "базова вартість",
                   "currency": "валюта туру", "is_featured": "рекомендований тур"}

FLIGHT_RE = re.compile(r"^[A-Z0-9]{2} ?\d{1,4}[A-Z]?$")   # e.g. QU 4433, PS101
MAX_TITLE = 200
MAX_DESCRIPTION = 5000                                    # form 4.6.2.1, field 16
MAX_DAY_TEXT = 2000
MAX_MONEY = Decimal("9999999999.99")                      # fits Numeric(12, 2)


def _error(message: str, status_code: int = 422) -> DomainError:
    return DomainError(message, status_code)


# ---------- reading
def get_tour(db: Session, tour_id: int) -> Tour:
    tour = db.scalar(select(Tour).where(Tour.id == tour_id)
                     .options(selectinload(Tour.program_days), selectinload(Tour.images)))
    if tour is None:
        raise _error("Тур не знайдено", 404)
    return tour


def list_tours(db: Session, *, status: TourStatus | None, q: str | None, page: int,
               page_size: int) -> tuple[list[Tour], int]:
    """Back-office list: all tours of all managers, newest changes first."""
    query = select(Tour)
    if status is not None:
        query = query.where(Tour.status == status)
    if q:
        query = query.where(or_(Tour.title_uk.icontains(q, autoescape=True),
                                Tour.title_en.icontains(q, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Tour.updated_at.desc(), Tour.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


# ---------- validation
def _check_hotel(db: Session, hotel_id: int) -> Hotel:
    hotel = db.get(Hotel, hotel_id)
    if hotel is None:
        raise _error("Готель не знайдено")
    if hotel.is_archived or hotel.resort.is_archived:
        raise _error("Готель або курорт архівний — оберіть інший")
    return hotel


def _check_city(db: Session, city_id: int) -> None:
    city = db.get(City, city_id)
    if city is None or city.is_archived:
        raise _error("Місто відправлення не знайдено")


def _normalize_flight(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.upper().split())
    if not value:
        return None
    if not FLIGHT_RE.match(value):
        raise _error("Номер рейсу має формат на кшталт QU 4433")
    return value


def _check_fields(db: Session, d: dict[str, Any], seats_sold: int) -> dict[str, Any]:
    """Validate and normalise all editable fields of a tour. Returns the cleaned values."""
    for field, label in REQUIRED_LABELS.items():
        if d.get(field) is None:
            raise _error(f"Заповніть обов'язкове поле: {label}")

    d["title_en"] = d["title_en"].strip()
    if not d["title_en"]:
        raise _error("Заповніть обов'язкове поле: назва туру англійською")
    hotel = _check_hotel(db, d["hotel_id"])
    # Form 4.6.2.1, field 1: the Ukrainian title is generated as "Hotel + Resort" when left empty.
    d["title_uk"] = (d.get("title_uk") or "").strip() or f"{hotel.name}, {hotel.resort.name_uk}"
    if len(d["title_uk"]) > MAX_TITLE or len(d["title_en"]) > MAX_TITLE:
        raise _error(f"Назва туру — не довше {MAX_TITLE} символів")

    transport = d["transport_type"]
    if transport in (TransportType.AIR, TransportType.BUS) and d.get("departure_city_id") is None:
        raise _error("Для авіа та автобуса вкажіть місто відправлення")
    if d.get("departure_city_id") is not None:
        _check_city(db, d["departure_city_id"])
    d["flight_out"] = _normalize_flight(d.get("flight_out"))
    d["flight_back"] = _normalize_flight(d.get("flight_back"))
    if transport != TransportType.AIR and (d["flight_out"] or d["flight_back"]):
        raise _error("Номери рейсів вказуються лише для авіаперельоту")

    if d["departure_to"] < d["departure_from"]:
        raise _error("Дата заїзду «до» не може бути раніше дати «від»")
    if not 1 <= d["nights"] <= 30:
        raise _error("Тривалість туру — від 1 до 30 ночей")
    if d["seats_total"] < 1:
        raise _error("Жорсткий блок місць — не менше 1")
    if d["seats_total"] < seats_sold:
        raise _error(f"Квота не може бути меншою за вже продані місця ({seats_sold})")
    if not Decimal(0) < d["base_price"] <= MAX_MONEY:
        raise _error("Базова вартість має бути більшою за 0")
    if d.get("child_price") is not None and not Decimal(0) <= d["child_price"] <= MAX_MONEY:
        raise _error("Ціна для дитини не може бути від'ємною")
    if d.get("description") is not None and len(d["description"]) > MAX_DESCRIPTION:
        raise _error(f"Опис туру — не довше {MAX_DESCRIPTION} символів")
    return d


def _check_program(days: list[dict[str, Any]], nights: int) -> list[tuple[int, str]]:
    """Form 4.6.2.1, field 17: days are numbered 1, 2, 3... without gaps; a tour of N nights
    has at most N + 1 days."""
    numbers = sorted(day["day_number"] for day in days)
    if numbers != list(range(1, len(days) + 1)):
        raise _error("Дні програми мають іти по порядку без пропусків і повторів: 1, 2, 3…")
    if len(days) > nights + 1:
        raise _error(f"Програма не може бути довшою за тур: максимум {nights + 1} дн.")
    result = []
    for day in sorted(days, key=lambda item: item["day_number"]):
        text = (day["description"] or "").strip()
        if not text:
            raise _error("Опишіть маршрут для кожного дня програми")
        if len(text) > MAX_DAY_TEXT:
            raise _error(f"Опис дня програми — не довше {MAX_DAY_TEXT} символів")
        result.append((day["day_number"], text))
    return result


def _ensure_draft(tour: Tour) -> None:
    """ТЗ 4.4.1: an active tour goes back to «Чернетка» for editing."""
    if tour.status == TourStatus.ARCHIVED:
        raise _error("Архівний тур змінювати не можна — створіть його копію", 409)
    if tour.status != TourStatus.DRAFT:
        raise _error("Редагувати можна лише чернетку — спершу зніміть тур з публікації", 409)


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
    days = changes.pop("program_days", None)
    merged = {field: getattr(tour, field) for field in TOUR_FIELDS} | changes
    fields = _check_fields(db, merged, tour.seats_sold)
    # Re-check the existing program too: fewer nights may make it too long.
    program = _check_program(days if days is not None else _current_program(tour), fields["nights"])
    for field, value in fields.items():
        setattr(tour, field, value)
    if days is not None:
        tour.program_days = [TourProgramDay(day_number=n, description=text) for n, text in program]
    db.flush()
    return tour


def change_status(db: Session, tour: Tour, new_status: TourStatus, user: User) -> Tour:
    """The only place where a tour status changes; every change goes to audit_log (ТЗ 4.4.1)."""
    old_status = tour.status
    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise _error(f"Неможливо змінити статус туру з «{STATUS_LABELS[old_status]}» "
                     f"на «{STATUS_LABELS[new_status]}»", 409)
    if new_status == TourStatus.ACTIVE:
        _validate_for_publish(db, tour)
    tour.status = new_status
    db.add(AuditLog(user_id=user.id, entity="tour", entity_id=str(tour.id), action="status_change",
                    old_value={"status": old_status.value}, new_value={"status": new_status.value}))
    db.flush()
    return tour


def _validate_for_publish(db: Session, tour: Tour) -> None:
    """Scenario 4.5.2, option 4.3 «Опублікувати»: full validation before the tour goes public.
    Re-runs the form checks because the hotel or city may have been archived since saving."""
    _check_fields(db, {field: getattr(tour, field) for field in TOUR_FIELDS}, tour.seats_sold)
    _check_program(_current_program(tour), tour.nights)
    # A range is still sellable while at least its last start date is ahead.
    if tour.departure_to < date.today():
        raise _error("Усі дати заїздів уже минули — оновіть дати перед публікацією")


def copy_tour(db: Session, source: Tour, manager: User) -> Tour:
    """New draft with the same content; nothing is sold yet. Photos are copied as files."""
    fields = {field: getattr(source, field) for field in TOUR_FIELDS}
    fields["title_uk"] = (source.title_uk[:MAX_TITLE - 9] + " (копія)")
    fields["title_en"] = (source.title_en[:MAX_TITLE - 7] + " (copy)")
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
    _ensure_draft(tour)
    if sorted(image_ids) != sorted(image.id for image in tour.images):
        raise _error("Передайте всі фото туру, кожне по одному разу")
    position = {image_id: i for i, image_id in enumerate(image_ids)}
    for image in tour.images:
        image.sort_order = position[image.id]
    db.flush()
    db.refresh(tour, ["images"])  # re-read in the new order
    return tour
