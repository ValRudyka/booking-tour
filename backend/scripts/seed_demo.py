"""Demo data for development, in Ukrainian: 10 fictional hotels with their facts, 28 tours with
generated photos, 2 promo codes, and 9 trips that already took place (completed orders by demo
clients, with published reviews and review photos).

Dev only: refuses to run unless APP_ENV is development/test (scripts/dev_guard.py).

Usage (from backend/):
    python -m scripts.seed_demo                    # create what is missing (safe to repeat)
    python -m scripts.seed_demo --reset            # remove only what the seed created
    python -m scripts.seed_demo --remove-legacy    # remove the old v1 demo hotels and tours

Data: scripts/data/hotels_uk.json (hotels, matched by `key`) and scripts/data/tours_uk.json
(tours, «Що включено / не включено» per transport type, past trips with their reviews).

How the seed knows what it created (needed for --reset):
- it works as dedicated, blocked accounts: «Демо-дані Адміністратор» creates resorts and hotels
  through services/reference_admin.py (the admin's own validation and audit log), and «Демо-дані
  Менеджер» creates tours (services/tours.py) and promo codes (services/promo_admin.py) and handles
  the demo orders; admin and manager duties stay separate, as in ТЗ 7. The accounts are blocked
  and have a random password, so nobody can sign in with them;
- seed tours / promo codes = created_by the seed manager; seed resorts / hotels = rows with a
  «created» entry by the seed admin in audit_log; seed tour photos = a «tour_image created» entry
  by the seed manager (photos someone uploads by hand to a seed tour have none);
- past trips are ordered by four blocked demo clients (fictional names): every order, payment,
  review and notification of theirs is seed data. Their payments have payments.origin = demo_seed,
  so finance pages and reports can leave them out (no money moved).

Idempotent: a hotel is found by name in its resort (an existing one is reused, never changed),
a tour by (seed manager, Ukrainian title), a promo code by its code, a past trip by (demo client,
tour, start date). Existing rows are never updated: on a database seeded by an older version, run
--reset and then the seed again to get the new data.

--reset removes the demo clients' orders (with their payments, reviews, review photo files and
notifications; hotel ratings are recalculated and seats_sold is corrected on a tour that stays)
and the seed's own tour photos (files too). The application itself never deletes orders: this is
a dev-only tool, and every deleted order is written to the audit log. Beyond that it never deletes
what someone else uses: a seed tour with other people's orders, reviews, favourites or hand-uploaded
photos is archived instead of deleted; a seed hotel or resort that is still used (e.g. by such a
tour or by your own hotel) is left as it is. The seed accounts stay, because the append-only audit
log refers to them.

Only Ukrainian data: the site is Ukrainian by default. tours.title_en is a required column
(form 4.6.2.1, field 2), so it holds the Ukrainian title until feature/i18n-en.

Hotel facts (beach line, distances, check-in/out, amenities, room types) go to their own columns
(form 4.6.4.2). The hotel's meal plan from the JSON becomes the meal plan of its tours: it belongs
to the tour (form 4.6.2.1). Insurance and transfer are never «included»: they are chosen and paid
at checkout (form 4.6.1.2).

Photos are generated locally (scripts/placeholder_images.py): nothing is downloaded.
"""
import argparse
import io
import json
import secrets
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (AuditLog, City, Country, Hotel, InsuranceType, Notification, Order,
                        OrderStatusHistory, OrderTourist, Payment, PromoCode, Resort, Review, Tour,
                        TourImage, TransferType, User)
from app.models.enums import (Currency, DiscountType, MealPlan, NameDisplay, OrderStatus,
                              PaymentMethod, PaymentOrigin, PaymentType, ReviewStatus, TourStatus,
                              TransactionStatus, TransportType, UserRole)
from app.services import images as image_files
from app.services import order_status, private_files, promo_admin, reference_admin
from app.services import orders as order_service
from app.services import reviews as review_service
from app.services import tours as tour_service
from app.services.audit import audit, snapshot
from app.services.clock import today
from app.services.errors import DomainError
from app.services.payments.service import apply_received_money
from app.services.pricing import calculate
from app.services.seats import lock_tour
from scripts.dev_guard import dev_guard_error
from scripts.placeholder_images import scene_png

DATA_DIR = Path(__file__).resolve().parent / "data"
HOTELS_FILE = DATA_DIR / "hotels_uk.json"
TOURS_FILE = DATA_DIR / "tours_uk.json"

SEED_ADMIN = dict(phone="+380000000901", email="seed-admin@tour.local", role=UserRole.ADMIN,
                  last_name="Демо-дані", first_name="Адміністратор")
SEED_MANAGER = dict(phone="+380000000902", email="seed-manager@tour.local", role=UserRole.MANAGER,
                    last_name="Демо-дані", first_name="Менеджер")
# Demo clients of the trips that already took place: blocked, random password, fictional names.
SEED_CLIENTS = [
    dict(phone=f"+38000000091{n}", email=f"seed-client-{n}@tour.local", role=UserRole.CLIENT,
         last_name=last, first_name=first)
    for n, (last, first) in enumerate([("Коваленко", "Олена"), ("Мельник", "Андрій"),
                                       ("Бондар", "Ірина"), ("Шевчук", "Тарас")], start=1)
]
# Fellow travellers in passport spelling (form 4.6.1.2): (last, first) per client, two each.
DEMO_TRAVELLERS = {1: [("KOVALENKO", "OLENA"), ("KOVALENKO", "MAKSYM")],
                   2: [("MELNYK", "ANDRII"), ("MELNYK", "SOFIIA")],
                   3: [("BONDAR", "IRYNA"), ("BONDAR", "OLEH")],
                   4: [("SHEVCHUK", "TARAS"), ("SHEVCHUK", "KATERYNA")]}
TOUR_PHOTOS = 3
DEMO_PAYMENT_NOTE = "Демо-дані (scripts.seed_demo): гроші не надходили"

# The only resorts the seed may create (country name_uk, resort name_uk). Any other resort from
# the JSON must already exist: a missing one means the reference data is not migrated (e.g.
# «Аланія» before the b7e2d4a91c55 migration), and creating it would make a duplicate.
NEW_RESORTS = {("Іспанія", "Салоу"), ("Болгарія", "Золоті Піски")}

PROMO_CODES = [  # form 4.6.2.3; valid from the run date for ~6 months
    dict(code="DEMO10", discount_type=DiscountType.PERCENT, discount_value=Decimal("10"),
         min_order_uah=None, usage_limit=None),
    dict(code="DEMO1500", discount_type=DiscountType.FIXED, discount_value=Decimal("1500"),
         min_order_uah=Decimal("30000"), usage_limit=100),
]
PROMO_DAYS = 182

# v1 of this script (before feature/demo-seed) created these by name, with real hotel brands.
# Only --remove-legacy touches them: (resort name_en, hotel name) and tour title_en.
LEGACY_HOTELS = [("Antalya", "Rixos Downtown Antalya"), ("Kemer", "Akra Kemer"),
                 ("Hurghada", "Steigenberger Aqua Magic"), ("Budva", "Hotel Budva Inn"),
                 ("Crete", "Aldemar Knossos Royal")]
LEGACY_TOURS = ["Antalya: Rixos Downtown, all inclusive", "Kemer: Akra, family holiday",
                "Hurghada: Steigenberger Aqua Magic", "Budva by bus from Kyiv"]

# Rows that belong to the tour itself and go with it (ondelete CASCADE, written by the seed).
TOUR_OWN_ROWS = {"tour_program_days.tour_id"}


# ---------- data files
def _data(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_hotels() -> list[dict[str, Any]]:
    return _data(HOTELS_FILE)["hotels"]


def load_tours() -> list[dict[str, Any]]:
    return _data(TOURS_FILE)["tours"]


def load_list_defaults() -> dict[str, dict[str, list[str]]]:
    """«Що включено / не включено» per transport type (tours_uk.json)."""
    data = _data(TOURS_FILE)
    return {"included": data["included_by_transport"], "excluded": data["excluded_by_transport"]}


def hotel_fields(h: dict[str, Any]) -> dict[str, Any]:
    """The hotel's description and facts (form 4.6.4.2) from hotels_uk.json."""
    return {"description": h["description"], "beach_line": h["beach_line"],
            "distance_to_beach_m": h["distance_to_beach_m"],
            "distance_to_airport_km": h["distance_to_airport_km"],
            "check_in": time.fromisoformat(h["check_in"]),
            "check_out": time.fromisoformat(h["check_out"]),
            "amenities": h["amenities"], "room_types": h["room_types"]}


def _kyiv(day: date, hour: int = 10, minute: int = 0) -> datetime:
    """A moment of a business day, for backdating demo rows."""
    return datetime.combine(day, time(hour, minute), ZoneInfo(settings.business_timezone))


# ---------- seed accounts and provenance
def _account(db: Session, spec: dict[str, Any], create: bool) -> User | None:
    user = db.scalar(select(User).where(User.email == spec["email"]))
    if user is None and create:
        # Blocked, with a random password nobody knows: the account only signs the seed's rows.
        user = User(**spec, password_hash=hash_password(secrets.token_urlsafe(32)), is_active=False)
        db.add(user)
        db.flush()
    return user


def seed_accounts(db: Session, create: bool = True) -> tuple[User | None, User | None]:
    return _account(db, SEED_ADMIN, create), _account(db, SEED_MANAGER, create)


def seed_clients(db: Session, create: bool = True) -> list[User | None]:
    """The four demo clients, in SEED_CLIENTS order (None for a missing one when create=False)."""
    return [_account(db, spec, create) for spec in SEED_CLIENTS]


def _created_by(db: Session, user: User | None, entity: str) -> set[int]:
    """Ids of rows of `entity` that `user` created (from audit_log)."""
    if user is None:
        return set()
    ids = db.scalars(select(AuditLog.entity_id).where(
        AuditLog.user_id == user.id, AuditLog.entity == entity, AuditLog.action == "created"))
    return {int(i) for i in ids}


# ---------- seed
@dataclass
class SeedResult:
    resorts: int = 0
    hotels: int = 0
    tours: int = 0
    tour_photos: int = 0
    promo_codes: int = 0
    orders: int = 0
    reviews: int = 0


def _resort(db: Session, admin: User, country_name: str, resort_name: str, result: SeedResult) -> Resort:
    country = db.scalar(select(Country).where(Country.name_uk == country_name))
    if country is None:
        raise DomainError(f"Країну «{country_name}» не знайдено в довіднику", 422)
    resort = db.scalar(select(Resort).where(Resort.country_id == country.id,
                                            Resort.name_uk == resort_name))
    if resort is not None:
        return resort
    if (country_name, resort_name) not in NEW_RESORTS:
        raise DomainError(f"Курорт «{resort_name}» ({country_name}) не знайдено — "
                          f"виконайте alembic upgrade head", 422)
    resort = reference_admin.create_item(db, admin, "resorts",
                                         {"country_id": country.id, "name_uk": resort_name})
    result.resorts += 1
    return resort


def _add_tour_photos(db: Session, tour: Tour, manager: User, first_seed: int) -> int:
    """Generated photos for a new (still draft) tour; each is marked as the seed's in audit_log."""
    files = [(io.BytesIO(scene_png(first_seed + n)), f"demo-{n + 1}.png") for n in range(TOUR_PHOTOS)]
    images = tour_service.add_images(db, tour, files)
    for image in images:
        audit(db, manager, "tour_image", image.id, "created",
              new={"tour_id": tour.id, "file_path": image.file_path})
    return len(images)


def _create_tour(db: Session, t: dict[str, Any], index: int, hotel: Hotel, meal_plan: str,
                 defaults: dict[str, dict[str, list[str]]], manager: User, start: date,
                 result: SeedResult) -> Tour:
    city_id = None
    if t["city"] is not None:
        city_id = db.scalar(select(City.id).where(City.name_uk == t["city"]))
        if city_id is None:
            raise DomainError(f"Місто відправлення «{t['city']}» не знайдено в довіднику", 422)
    first = start + timedelta(days=t["start_in"])
    transport = TransportType(t["transport"])
    tour = tour_service.create_tour(db, {
        "title_uk": t["title"], "title_en": t["title"],  # Ukrainian only, see the docstring
        "hotel_id": hotel.id, "transport_type": transport,
        "departure_city_id": city_id, "flight_out": t["flight_out"],
        "flight_back": t["flight_back"], "departure_from": first,
        "departure_to": first + timedelta(days=t["span"]), "nights": t["nights"],
        "seats_total": t["seats_total"], "base_price": Decimal(t["base_price"]),
        "child_price": Decimal(t["child_price"]) if t["child_price"] else None,
        "currency": Currency(t["currency"]), "description": t["description"],
        "is_featured": t["featured"],
        "meal_plan": MealPlan((t.get("meal_plan") or meal_plan).lower()),
        "included": t.get("included") or defaults["included"][transport.value],
        "excluded": t.get("excluded") or defaults["excluded"][transport.value],
        "program_days": [{"day_number": n, "description": text}
                         for n, text in enumerate(t["program"], start=1)],
    }, manager)
    result.tour_photos += _add_tour_photos(db, tour, manager, first_seed=index * TOUR_PHOTOS)
    if t["status"] in ("active", "archived"):   # an archived tour was on sale once
        tour_service.change_status(db, tour, TourStatus.ACTIVE, manager)
    if t["status"] == "archived":
        tour_service.change_status(db, tour, TourStatus.ARCHIVED, manager)
    result.tours += 1
    return tour


def _default_service(db: Session, model) -> Any:
    return db.scalar(select(model).where(model.is_default.is_(True), model.is_archived.is_(False)))


def _backdate(order: Order, booked: datetime) -> None:
    """Plausible dates instead of "now" for a trip that happened weeks ago."""
    at = {OrderStatus.CHECKOUT: booked,
          OrderStatus.AWAITING_PAYMENT: booked + timedelta(minutes=5),
          OrderStatus.PAID: booked + timedelta(minutes=12),
          OrderStatus.IN_PROGRESS: booked + timedelta(hours=20),
          OrderStatus.CONFIRMED: booked + timedelta(days=2),
          OrderStatus.DOCUMENTS_READY: _kyiv(order.start_date - timedelta(days=5), 15),
          OrderStatus.COMPLETED: _kyiv(order.end_date + timedelta(days=1), 3)}
    order.created_at = booked
    for row in order.history:
        row.changed_at = at[OrderStatus(row.new_status)]
    for payment in order.payments:
        payment.created_at = payment.received_at = at[OrderStatus.PAID] - timedelta(minutes=1)


def _past_trip(db: Session, tour: Tour, trip: dict[str, Any], clients: list[User], manager: User,
               photo_seed: int, result: SeedResult) -> None:
    """A trip that already took place: a completed order of a demo client and, if given, a
    published review. Statuses, quota and history go through the real services; only the order
    row is written directly, because the order service accepts start dates from tomorrow only."""
    client = clients[trip["client"] - 1]
    start = tour.departure_from + timedelta(days=trip["start_offset"])
    if db.scalar(select(Order.id).where(Order.client_id == client.id, Order.tour_id == tour.id,
                                        Order.start_date == start)) is not None:
        return
    end = start + timedelta(days=tour.nights)
    if end >= today():
        raise DomainError(f"Демо-поїздка «{tour.title_uk}» з {start:%d.%m.%Y} ще не завершилась — "
                          f"перевірте start_offset у tours_uk.json", 422)

    travellers = DEMO_TRAVELLERS[trip["client"]]
    insurance, transfer = _default_service(db, InsuranceType), _default_service(db, TransferType)
    price = calculate(tour, order_service._rate(db, tour), len(travellers), 0, insurance, transfer)
    booked = _kyiv(start - timedelta(days=30))
    order = Order(number=order_service._next_number(db), client_id=client.id, tour_id=tour.id,
                  status=OrderStatus.CHECKOUT, start_date=start, end_date=end,
                  adults=len(travellers), children=0,
                  insurance_type_id=insurance.id if insurance else None,
                  transfer_type_id=transfer.id if transfer else None,
                  total_uah=price.total_uah, discount_uah=price.discount_uah, rate_used=price.rate,
                  offer_accepted_at=booked + timedelta(minutes=4))
    order.tourists = [OrderTourist(last_name_lat=last, first_name_lat=first,
                                   birth_date=date(1985 + n, 3 + n, 10 + n),
                                   passport_number=f"DM{trip['client']}{start:%y%m%d}{n}",
                                   passport_expiry=end + timedelta(days=5 * 365))
                      for n, (last, first) in enumerate(travellers)]
    db.add(order)
    db.flush()
    order_status.record_created(db, order, client)
    order_status.change_status(db, order, OrderStatus.AWAITING_PAYMENT, client)
    db.add(Payment(order_id=order.id, type=PaymentType.PAYMENT, method=PaymentMethod.CARD,
                   status=TransactionStatus.SUCCEEDED, amount_uah=order.total_uah,
                   paid_amount=order.total_uah, purpose=DEMO_PAYMENT_NOTE,
                   origin=PaymentOrigin.DEMO_SEED))
    db.flush()
    apply_received_money(db, order, None, DEMO_PAYMENT_NOTE)          # -> paid, seats_sold += 2
    order.manager_id = manager.id                                     # the manager took it
    order_status.change_status(db, order, OrderStatus.IN_PROGRESS, manager)
    order.pnr = f"DEMO{order.id:05d}"
    order_status.change_status(db, order, OrderStatus.CONFIRMED, manager)
    order_status.change_status(db, order, OrderStatus.DOCUMENTS_READY, manager)
    order_status.change_status(db, order, OrderStatus.COMPLETED, None)  # the System, after the trip
    db.refresh(order, ["history", "payments"])
    _backdate(order, booked)
    result.orders += 1

    spec = trip.get("review")
    if spec is None:
        return
    photos = [(io.BytesIO(scene_png(photo_seed + n)), f"review-{n + 1}.png") for n in range(spec["photos"])]
    review = review_service.create_review(db, client, order, {
        "hotel_rating": spec["hotel_rating"], "service_rating": spec["service_rating"],
        "positive": spec["positive"], "negative": spec["negative"],
        "name_display": NameDisplay(spec["name_display"])}, photos)
    if review.status == ReviewStatus.PENDING:
        review_service.publish(db, review, manager)                   # recalculates the hotel rating
    review.created_at = review.submitted_at = _kyiv(end + timedelta(days=2), 19)
    review.moderated_at = _kyiv(end + timedelta(days=3), 11)
    result.reviews += 1


def seed(db: Session) -> SeedResult:
    """Create what is missing. Flushes only; the caller commits."""
    result = SeedResult()
    admin, manager = seed_accounts(db)
    clients = seed_clients(db)
    defaults = load_list_defaults()

    hotels: dict[str, Hotel] = {}
    meal_plans: dict[str, str] = {}
    for h in load_hotels():
        resort = _resort(db, admin, h["country"], h["resort"], result)
        hotel = db.scalar(select(Hotel).where(Hotel.resort_id == resort.id, Hotel.name == h["name"]))
        if hotel is None:
            hotel = reference_admin.create_item(db, admin, "hotels", {
                "resort_id": resort.id, "name": h["name"], "stars": h["stars"], **hotel_fields(h)})
            result.hotels += 1
        hotels[h["key"]] = hotel
        meal_plans[h["key"]] = h["meal_plan"]

    start = today()
    for index, t in enumerate(load_tours()):
        tour = db.scalar(select(Tour).where(Tour.created_by == manager.id, Tour.title_uk == t["title"]))
        if tour is None:
            tour = _create_tour(db, t, index, hotels[t["hotel"]], meal_plans[t["hotel"]], defaults,
                                manager, start, result)
        for n, trip in enumerate(t.get("past_trips", [])):
            _past_trip(db, tour, trip, clients, manager, photo_seed=1000 + index * 10 + n * 3,
                       result=result)

    for spec in PROMO_CODES:
        if db.scalar(select(PromoCode.id).where(PromoCode.code == spec["code"])) is None:
            promo_admin.create_code(db, manager, spec | {
                "valid_from": start, "valid_to": start + timedelta(days=PROMO_DAYS), "is_active": True})
            result.promo_codes += 1
    return result


# ---------- reset
@dataclass
class ResetResult:
    deleted: dict[str, int] = field(default_factory=lambda: {
        "orders": 0, "reviews": 0, "tour_photos": 0, "tours": 0, "hotels": 0, "resorts": 0,
        "promo_codes": 0})
    kept: list[str] = field(default_factory=list)   # what stayed and why


def _remove_demo_trips(db: Session, manager: User, clients: list[User], result: ResetResult) -> None:
    """Every order of the demo clients, with its payments, review (photo files too) and
    notifications. Seats sold by these orders go back to the tour, which may stay (see _remove_tour)."""
    client_ids = [c.id for c in clients]
    if not client_ids:
        return
    hotels: set[int] = set()
    for order in db.scalars(select(Order).where(Order.client_id.in_(client_ids)).order_by(Order.id)).all():
        review = db.scalar(select(Review).where(Review.order_id == order.id))
        if review is not None:
            hotels.add(review.hotel_id)
            for photo in review.photos:
                private_files.remove(photo.file_path)
            db.delete(review)
            result.deleted["reviews"] += 1
        was_sold = db.scalar(select(func.count()).where(
            OrderStatusHistory.order_id == order.id,
            OrderStatusHistory.new_status == OrderStatus.PAID.value)) > 0
        if was_sold and order.status not in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            lock_tour(db, order.tour_id).seats_sold -= order.adults + order.children
        for payment in list(order.payments):
            db.delete(payment)
        for note in db.scalars(select(Notification).where(Notification.order_id == order.id)).all():
            db.delete(note)
        db.flush()
        audit(db, manager, "order", order.id, "deleted",
              old={"number": order.number, "client_id": order.client_id, "tour_id": order.tour_id,
                   "status": order.status, "reason": "scripts.seed_demo --reset"})
        db.delete(order)           # tourists, history and documents go with it
        result.deleted["orders"] += 1
    db.flush()
    for note in db.scalars(select(Notification).where(Notification.user_id.in_(client_ids))).all():
        db.delete(note)
    db.flush()
    for hotel_id in sorted(hotels):
        review_service.recalc_hotel_rating(db, hotel_id)


def _remove_seed_photos(db: Session, manager: User, result: ResetResult) -> None:
    """Only the photos the seed generated (audit entry); hand-uploaded ones stay."""
    for image_id in sorted(_created_by(db, manager, "tour_image")):
        image = db.get(TourImage, image_id)
        if image is None:
            continue
        image_files.remove_files([image.file_path])
        audit(db, manager, "tour_image", image.id, "deleted", old={"tour_id": image.tour_id})
        db.delete(image)
        result.deleted["tour_photos"] += 1
    db.flush()


def _remove_tour(db: Session, tour: Tour, user: User, result: ResetResult) -> None:
    """Delete a tour nobody uses; archive (keep) a tour with orders, reviews, favourites, photos."""
    db.refresh(tour)
    used = {k: v for k, v in reference_admin.references(db, "tours", tour.id).items()
            if k not in TOUR_OWN_ROWS}
    if used:
        if tour.status != TourStatus.ARCHIVED:
            tour_service.change_status(db, tour, TourStatus.ARCHIVED, user)
        result.kept.append(f"tour {tour.id} «{tour.title_uk}» archived, used by: {', '.join(used)}")
        return
    tour_id, old = tour.id, snapshot(tour, ("title_uk", "hotel_id", "status"))
    db.delete(tour)   # its program days go with it (cascade)
    db.flush()
    audit(db, user, "tour", tour_id, "deleted", old=old)
    result.deleted["tours"] += 1


def _remove_reference(db: Session, admin: User, kind: str, item, result: ResetResult,
                      archive_if_used: bool) -> None:
    table = reference_admin.KINDS[kind].model.__tablename__
    used = reference_admin.references(db, table, item.id)
    label = getattr(item, "name", None) or item.name_uk
    if not used:
        reference_admin.delete_item(db, admin, kind, item.id)
        result.deleted[kind] += 1
    elif archive_if_used:
        reference_admin.set_archived(db, admin, kind, item.id, True)
        result.kept.append(f"{kind[:-1]} «{label}» archived, used by: {', '.join(used)}")
    else:
        result.kept.append(f"{kind[:-1]} «{label}» kept, used by: {', '.join(used)}")


def reset(db: Session) -> ResetResult:
    """Remove only what the seed created (see the module docstring). Flushes only."""
    result = ResetResult()
    admin, manager = seed_accounts(db, create=False)
    clients = [c for c in seed_clients(db, create=False) if c is not None]
    if manager is not None:
        _remove_demo_trips(db, manager, clients, result)
        _remove_seed_photos(db, manager, result)
        for tour in db.scalars(select(Tour).where(Tour.created_by == manager.id).order_by(Tour.id)).all():
            _remove_tour(db, tour, manager, result)
        for promo in db.scalars(select(PromoCode).where(PromoCode.created_by == manager.id)).all():
            if promo_admin.ever_used(db, promo):
                if promo.is_active:
                    promo_admin.update_code(db, manager, promo.id, {"is_active": False})
                result.kept.append(f"promo code {promo.code} deactivated, used by orders")
            else:
                promo_admin.delete_code(db, manager, promo.id)
                result.deleted["promo_codes"] += 1
    if admin is not None:
        # Hotels first: a resort is free only after its seed hotels are gone.
        for entity, kind in (("hotel", "hotels"), ("resort", "resorts")):
            model = reference_admin.KINDS[kind].model
            for item_id in sorted(_created_by(db, admin, entity)):
                item = db.get(model, item_id)
                if item is not None:
                    _remove_reference(db, admin, kind, item, result, archive_if_used=False)
    return result


def remove_legacy(db: Session) -> ResetResult:
    """Remove the v1 demo tours and hotels (matched by their exact names); archive used ones."""
    result = ResetResult()
    admin, manager = seed_accounts(db)
    for tour in db.scalars(select(Tour).where(Tour.title_en.in_(LEGACY_TOURS)).order_by(Tour.id)).all():
        _remove_tour(db, tour, manager, result)
    for resort_en, name in LEGACY_HOTELS:
        hotel = db.scalar(select(Hotel).join(Resort).where(Resort.name_en == resort_en,
                                                           Hotel.name == name))
        if hotel is not None:
            _remove_reference(db, admin, "hotels", hotel, result, archive_if_used=True)
    return result


# ---------- CLI
def _print_reset(title: str, result: ResetResult) -> None:
    print(f"{title}: deleted " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in result.deleted.items()))
    for line in result.kept:
        print(f"  kept: {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_demo",
                                     description="Dev only: fill the catalog with demo data.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", action="store_true", help="remove only what the seed created")
    group.add_argument("--remove-legacy", action="store_true",
                       help="remove the old v1 demo hotels and tours (real hotel names)")
    args = parser.parse_args(argv)

    refusal = dev_guard_error()
    if refusal:
        print(f"Refused: {refusal}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            if args.reset:
                outcome = reset(db)
            elif args.remove_legacy:
                outcome = remove_legacy(db)
            else:
                outcome = seed(db)
            db.commit()
        except DomainError as error:
            db.rollback()
            print(f"Refused: {error.message}", file=sys.stderr)
            return 1

    if isinstance(outcome, SeedResult):
        print(f"Created: resorts {outcome.resorts}, hotels {outcome.hotels}, tours {outcome.tours} "
              f"(photos {outcome.tour_photos}), promo codes {outcome.promo_codes}, past trips "
              f"{outcome.orders}, reviews {outcome.reviews} (existing ones were skipped)")
    else:
        _print_reset("Reset" if args.reset else "Legacy demo data", outcome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
