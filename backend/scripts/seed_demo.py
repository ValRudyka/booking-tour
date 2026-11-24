"""Demo data for development: 10 fictional hotels, 25 tours and 2 promo codes, in Ukrainian.

Dev only: refuses to run unless APP_ENV is development/test (scripts/dev_guard.py).

Usage (from backend/):
    python -m scripts.seed_demo                    # create what is missing (safe to repeat)
    python -m scripts.seed_demo --reset            # remove only what the seed created
    python -m scripts.seed_demo --remove-legacy    # remove the old v1 demo hotels and tours

Data: scripts/data/hotels_uk.json (hotels, matched by `key`) and scripts/data/tours_uk.json.

How the seed knows what it created (needed for --reset):
- it works as two dedicated, blocked accounts: «Демо-дані Адміністратор» creates resorts and
  hotels through services/reference_admin.py (the admin's own validation and audit log), and
  «Демо-дані Менеджер» creates tours (services/tours.py) and promo codes (services/promo_admin.py);
  admin and manager duties stay separate, as in ТЗ 7. The accounts are blocked and have a random
  password, so nobody can sign in with them;
- seed tours / promo codes = created_by the seed manager; seed resorts / hotels = rows with a
  «created» entry by the seed admin in audit_log.

Idempotent: a hotel is found by name in its resort (an existing one is reused, never changed),
a tour by (seed manager, Ukrainian title), a promo code by its code.

--reset never deletes what someone else uses: a seed tour with orders, reviews, favourites or
hand-uploaded photos is archived instead of deleted; a seed hotel or resort that is still used
(e.g. by such a tour or by your own hotel) is left as it is. The seed accounts stay, because the
append-only audit log refers to them.

Only Ukrainian data: the site is Ukrainian by default. tours.title_en is a required column
(form 4.6.2.1, field 2), so it holds the Ukrainian title until feature/i18n-en.

Hotel fields with no column in the ТЗ model (meal plan, beach line, distances, check-in/out,
amenities, room types) are written as a short block at the end of the hotel description; the
tour card shows the hotel description (form 4.6.2.1, field 5).
"""
import argparse
import json
import secrets
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import AuditLog, City, Country, Hotel, PromoCode, Resort, Tour, User
from app.models.enums import Currency, DiscountType, TourStatus, TransportType, UserRole
from app.services import promo_admin, reference_admin
from app.services import tours as tour_service
from app.services.audit import audit, snapshot
from app.services.clock import today
from app.services.errors import DomainError
from scripts.dev_guard import dev_guard_error

DATA_DIR = Path(__file__).resolve().parent / "data"
HOTELS_FILE = DATA_DIR / "hotels_uk.json"
TOURS_FILE = DATA_DIR / "tours_uk.json"

SEED_ADMIN = dict(phone="+380000000901", email="seed-admin@tour.local", role=UserRole.ADMIN,
                  last_name="Демо-дані", first_name="Адміністратор")
SEED_MANAGER = dict(phone="+380000000902", email="seed-manager@tour.local", role=UserRole.MANAGER,
                    last_name="Демо-дані", first_name="Менеджер")

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

LINE_NAMES = {1: "перша", 2: "друга", 3: "третя"}
# Rows that belong to the tour itself and go with it (ondelete CASCADE, written by the seed).
TOUR_OWN_ROWS = {"tour_program_days.tour_id"}


# ---------- data files
def load_hotels() -> list[dict[str, Any]]:
    return json.loads(HOTELS_FILE.read_text(encoding="utf-8"))["hotels"]


def load_tours() -> list[dict[str, Any]]:
    return json.loads(TOURS_FILE.read_text(encoding="utf-8"))["tours"]


def hotel_description(h: dict[str, Any]) -> str:
    """JSON description + the fields that have no column, as plain text lines."""
    beach = ("біля самого моря" if h["distance_to_beach_m"] == 0
             else f"{h['distance_to_beach_m']} м до моря")
    line = LINE_NAMES.get(h["beach_line"], str(h["beach_line"]))
    return "\n".join([
        h["description"],
        "",
        f"Харчування: {h['meal_plan_name']} ({h['meal_plan']}).",
        f"Пляж: {line} лінія, {beach}. До аеропорту — {h['distance_to_airport_km']} км.",
        f"Заїзд з {h['check_in']}, виїзд до {h['check_out']}.",
        f"Зручності: {', '.join(h['amenities'])}.",
        f"Типи номерів: {', '.join(h['room_types'])}.",
    ])


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


def _created_by(db: Session, admin: User | None, entity: str) -> set[int]:
    """Ids of resorts / hotels that the seed admin created (from audit_log)."""
    if admin is None:
        return set()
    ids = db.scalars(select(AuditLog.entity_id).where(
        AuditLog.user_id == admin.id, AuditLog.entity == entity, AuditLog.action == "created"))
    return {int(i) for i in ids}


# ---------- seed
@dataclass
class SeedResult:
    resorts: int = 0
    hotels: int = 0
    tours: int = 0
    promo_codes: int = 0


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


def seed(db: Session) -> SeedResult:
    """Create what is missing. Flushes only; the caller commits."""
    result = SeedResult()
    admin, manager = seed_accounts(db)

    hotels: dict[str, Hotel] = {}
    for h in load_hotels():
        resort = _resort(db, admin, h["country"], h["resort"], result)
        hotel = db.scalar(select(Hotel).where(Hotel.resort_id == resort.id, Hotel.name == h["name"]))
        if hotel is None:
            hotel = reference_admin.create_item(db, admin, "hotels", {
                "resort_id": resort.id, "name": h["name"], "stars": h["stars"],
                "description": hotel_description(h)})
            result.hotels += 1
        hotels[h["key"]] = hotel

    start = today()
    for t in load_tours():
        exists = db.scalar(select(Tour.id).where(Tour.created_by == manager.id,
                                                 Tour.title_uk == t["title"]))
        if exists is not None:
            continue
        city_id = None
        if t["city"] is not None:
            city_id = db.scalar(select(City.id).where(City.name_uk == t["city"]))
            if city_id is None:
                raise DomainError(f"Місто відправлення «{t['city']}» не знайдено в довіднику", 422)
        first = start + timedelta(days=t["start_in"])
        tour = tour_service.create_tour(db, {
            "title_uk": t["title"], "title_en": t["title"],  # Ukrainian only, see the docstring
            "hotel_id": hotels[t["hotel"]].id, "transport_type": TransportType(t["transport"]),
            "departure_city_id": city_id, "flight_out": t["flight_out"],
            "flight_back": t["flight_back"], "departure_from": first,
            "departure_to": first + timedelta(days=t["span"]), "nights": t["nights"],
            "seats_total": t["seats_total"], "base_price": Decimal(t["base_price"]),
            "child_price": Decimal(t["child_price"]) if t["child_price"] else None,
            "currency": Currency(t["currency"]), "description": t["description"],
            "is_featured": t["featured"],
            "program_days": [{"day_number": n, "description": text}
                             for n, text in enumerate(t["program"], start=1)],
        }, manager)
        if t["status"] in ("active", "archived"):   # an archived tour was on sale once
            tour_service.change_status(db, tour, TourStatus.ACTIVE, manager)
        if t["status"] == "archived":
            tour_service.change_status(db, tour, TourStatus.ARCHIVED, manager)
        result.tours += 1

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
        "tours": 0, "hotels": 0, "resorts": 0, "promo_codes": 0})
    kept: list[str] = field(default_factory=list)   # what stayed and why


def _remove_tour(db: Session, tour: Tour, user: User, result: ResetResult) -> None:
    """Delete a tour nobody uses; archive (keep) a tour with orders, reviews, favourites, photos."""
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
    if manager is not None:
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
    d = result.deleted
    print(f"{title}: deleted tours {d['tours']}, hotels {d['hotels']}, resorts {d['resorts']}, "
          f"promo codes {d['promo_codes']}")
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
        print(f"Created: resorts {outcome.resorts}, hotels {outcome.hotels}, tours {outcome.tours}, "
              f"promo codes {outcome.promo_codes} (existing ones were skipped)")
    else:
        _print_reset("Reset" if args.reset else "Legacy demo data", outcome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
