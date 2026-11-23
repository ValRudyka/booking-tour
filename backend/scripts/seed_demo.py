"""Demo data for a working catalog: hotels and a few published tours.

Hotels are reference data managed by the admin (feature/admin); until that exists this script
fills them so the catalog can be demonstrated. Tours are created through the same services as
the API (validation + audit_log), owned by an existing manager.

Usage (from backend/):
    python -m scripts.create_user --role manager --phone +380500000002 --email manager@tour.local \
        --password "Manager-pass-1" --last-name Менеджер --first-name Демо
    python -m scripts.seed_demo                       # uses the first manager in the database
    python -m scripts.seed_demo --manager-phone +380500000002

Safe to run again: hotels and tours that already exist (matched by name) are skipped.
"""
import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import City, Hotel, Resort, Tour, User
from app.models.enums import Currency, TourStatus, TransportType, UserRole
from app.services import tours as tour_service

HOTELS = [  # resort (en), name, stars, description
    ("Antalya", "Rixos Downtown Antalya", 5, "Готель на першій лінії, власний пляж, все включено."),
    ("Kemer", "Akra Kemer", 4, "Сімейний готель біля гір, дитячий клуб, аквапарк."),
    ("Hurghada", "Steigenberger Aqua Magic", 5, "Великий аквапарк, кораловий риф поруч."),
    ("Budva", "Hotel Budva Inn", 3, "Затишний готель у старому місті, 300 м до моря."),
    ("Crete", "Aldemar Knossos Royal", 5, "Курортний комплекс із піщаним пляжем."),
]

TOURS = [
    dict(title_en="Antalya: Rixos Downtown, all inclusive", hotel="Rixos Downtown Antalya",
         transport_type=TransportType.AIR, city="Warsaw", flight_out="LO 3021", flight_back="LO 3022",
         start_in=21, span=60, nights=7, seats_total=40, base_price="850.00", child_price="425.00",
         currency=Currency.EUR, is_featured=True,
         program=["Переліт Варшава — Анталія, трансфер, заселення",
                  "Відпочинок на пляжі", "Екскурсія до старого міста Калеїчі"]),
    dict(title_en="Kemer: Akra, family holiday", hotel="Akra Kemer", transport_type=TransportType.AIR,
         city="Krakow", flight_out="FR 2140", flight_back="FR 2141", start_in=35, span=45, nights=10,
         seats_total=25, base_price="690.00", child_price=None, currency=Currency.EUR,
         is_featured=False, program=[]),
    dict(title_en="Hurghada: Steigenberger Aqua Magic", hotel="Steigenberger Aqua Magic",
         transport_type=TransportType.AIR, city="Katowice", flight_out="SM 3412", flight_back="SM 3413",
         start_in=14, span=90, nights=7, seats_total=30, base_price="980.00", child_price="490.00",
         currency=Currency.USD, is_featured=True, program=[]),
    dict(title_en="Budva by bus from Kyiv", hotel="Hotel Budva Inn", transport_type=TransportType.BUS,
         city="Kyiv", flight_out=None, flight_back=None, start_in=10, span=30, nights=6,
         seats_total=45, base_price="18500.00", child_price="14000.00", currency=Currency.UAH,
         is_featured=False,
         program=["Виїзд з Києва", "Прибуття, заселення", "Старе місто Будви",
                  "Вільний день", "Екскурсія до Котора", "Вільний день", "Виїзд додому"]),
]


def _find_manager(db: Session, phone: str | None) -> User | None:
    query = select(User).where(User.role == UserRole.MANAGER, User.is_active.is_(True))
    if phone:
        query = query.where(User.phone == phone)
    return db.scalars(query.order_by(User.id)).first()


def seed(db: Session, manager: User) -> tuple[int, int]:
    """Create missing hotels and tours. Returns (hotels_created, tours_created)."""
    hotels_created = tours_created = 0
    hotels: dict[str, Hotel] = {}
    for resort_en, name, stars, description in HOTELS:
        resort = db.scalar(select(Resort).where(Resort.name_en == resort_en))
        hotel = db.scalar(select(Hotel).where(Hotel.resort_id == resort.id, Hotel.name == name))
        if hotel is None:
            hotel = Hotel(resort_id=resort.id, name=name, stars=stars, description=description)
            db.add(hotel)
            db.flush()
            hotels_created += 1
        hotels[name] = hotel

    for spec in TOURS:
        if db.scalar(select(Tour.id).where(Tour.title_en == spec["title_en"])) is not None:
            continue
        start = date.today() + timedelta(days=spec["start_in"])
        city_id = db.scalar(select(City.id).where(City.name_en == spec["city"]))
        data = dict(
            title_uk=None,  # generated as "Hotel, Resort" (form 4.6.2.1, field 1)
            title_en=spec["title_en"], hotel_id=hotels[spec["hotel"]].id,
            transport_type=spec["transport_type"], departure_city_id=city_id,
            flight_out=spec["flight_out"], flight_back=spec["flight_back"],
            departure_from=start, departure_to=start + timedelta(days=spec["span"]),
            nights=spec["nights"], seats_total=spec["seats_total"],
            base_price=Decimal(spec["base_price"]),
            child_price=Decimal(spec["child_price"]) if spec["child_price"] else None,
            currency=spec["currency"], description=hotels[spec["hotel"]].description,
            is_featured=spec["is_featured"],
            program_days=[{"day_number": i, "description": text}
                          for i, text in enumerate(spec["program"], start=1)],
        )
        tour = tour_service.create_tour(db, data, manager)
        tour_service.change_status(db, tour, TourStatus.ACTIVE, manager)
        tours_created += 1
    return hotels_created, tours_created


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill demo hotels and tours")
    parser.add_argument("--manager-phone", help="Owner of the demo tours (default: first manager)")
    args = parser.parse_args()
    with SessionLocal() as db:
        manager = _find_manager(db, args.manager_phone)
        if manager is None:
            print("No active manager found. Create one first:\n  python -m scripts.create_user "
                  "--role manager --phone ... --email ... --password ... --last-name ... "
                  "--first-name ...", file=sys.stderr)
            return 1
        hotels_created, tours_created = seed(db, manager)
        db.commit()
    print(f"Hotels created: {hotels_created}, tours created and published: {tours_created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
