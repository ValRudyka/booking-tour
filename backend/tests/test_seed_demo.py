"""Demo seed (scripts.seed_demo): dev guard, the catalog it builds, idempotency, --reset safety."""
import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import AuditLog, Hotel, PromoCode, Resort, Tour
from app.models.enums import TourStatus
from scripts import complete_orders, seed_demo
from scripts.seed_demo import (LEGACY_HOTELS, LEGACY_TOURS, load_hotels, load_tours, remove_legacy,
                               reset, seed, seed_accounts)
from tests.factories import make_hotel, make_order, make_tour


def _count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def _seed_tours(db):
    _admin, manager = seed_accounts(db, create=False)
    return db.scalars(select(Tour).where(Tour.created_by == manager.id)).all()


# ---------- data files
def test_data_files_are_consistent():
    hotels, tours = load_hotels(), load_tours()
    keys = [h["key"] for h in hotels]
    assert len(hotels) == 10 and len(set(keys)) == 10
    assert {h["meal_plan"] for h in hotels} <= {"UAI", "AI", "HB", "BB"}
    assert len(tours) == 25 and len({t["title"] for t in tours}) == 25
    for key in keys:
        assert 2 <= sum(t["hotel"] == key for t in tours) <= 3
    for t in tours:
        assert t["hotel"] in keys
        assert 3 <= len(t["program"]) <= 5 and 5 <= t["nights"] <= 14
        assert 20 <= t["start_in"] <= 182
    assert [t["status"] for t in tours].count("draft") == 2
    assert [t["status"] for t in tours].count("archived") == 1


# ---------- dev guard
@pytest.mark.parametrize("env, key", [("production", ""), ("development", "sk_live_123")])
def test_guard_refuses_outside_dev(monkeypatch, capsys, env, key):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "stripe_secret_key", key)

    def no_db():
        raise AssertionError("the database must not be touched")

    monkeypatch.setattr(seed_demo, "SessionLocal", no_db)
    for argv in ([], ["--reset"], ["--remove-legacy"]):
        assert seed_demo.main(argv) == 1
    assert "Refused" in capsys.readouterr().err


def test_force_complete_is_dev_only(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")

    def no_force(order_id):
        raise AssertionError("must be refused before completing anything")

    monkeypatch.setattr(complete_orders, "run_force_complete", no_force)
    assert complete_orders.main(["--order-id", "1", "--force"]) == 1


# ---------- what the seed builds
def test_seed_builds_catalog(client, db):
    result = seed(db)
    assert (result.resorts, result.hotels, result.tours, result.promo_codes) == (2, 10, 25, 2)

    tours = _seed_tours(db)
    statuses = [t.status for t in tours]
    assert statuses.count(TourStatus.ACTIVE) == 22
    assert statuses.count(TourStatus.DRAFT) == 2
    assert statuses.count(TourStatus.ARCHIVED) == 1
    assert sum(t.is_featured for t in tours) == 5
    assert all(t.title_en == t.title_uk and not t.images for t in tours)   # Ukrainian only, no photos
    assert all(3 <= len(t.program_days) <= 5 for t in tours)

    # Missing resorts went through the admin service (audit row by the seed admin);
    # Аланія is the migrated seeded resort, not a new one.
    admin, _manager = seed_accounts(db, create=False)
    assert not admin.is_active
    for name in ("Салоу", "Золоті Піски"):
        resort = db.scalar(select(Resort).where(Resort.name_uk == name))
        assert _count(db, AuditLog, AuditLog.user_id == admin.id, AuditLog.entity == "resort",
                      AuditLog.entity_id == str(resort.id), AuditLog.action == "created") == 1
    assert _count(db, Resort, Resort.name_uk == "Аланія") == 1
    assert _count(db, Resort, Resort.name_uk == "Аланья") == 0

    hotel = db.scalar(select(Hotel).where(Hotel.name == "Alanya Blue Coast"))
    assert hotel.resort.name_uk == "Аланія"
    assert "Харчування: Сніданок і вечеря (HB)." in hotel.description
    assert "Типи номерів: Стандартний номер, Номер з балконом." in hotel.description

    page1 = client.get("/api/tours", params={"page_size": 12}).json()
    page2 = client.get("/api/tours", params={"page_size": 12, "page": 2}).json()
    assert page1["total"] == 22 and len(page1["items"]) == 12 and len(page2["items"]) == 10
    cards = page1["items"] + page2["items"]
    assert [c["free_seats"] for c in cards].count(1) == 1
    assert client.get("/api/tours", params={"featured": True}).json()["total"] == 5


def test_seed_is_idempotent(db):
    seed(db)
    again = seed(db)
    assert (again.resorts, again.hotels, again.tours, again.promo_codes) == (0, 0, 0, 0)
    assert _count(db, Hotel) == 10
    assert _count(db, Tour) == 25
    assert _count(db, PromoCode) == 2


def test_seed_reuses_an_existing_hotel(db):
    own = make_hotel(db, name="Coral Bay Resort", resort_en="Hurghada", description="Мій опис")
    assert seed(db).hotels == 9
    assert db.get(Hotel, own.id).description == "Мій опис"   # reused, not changed
    assert _count(db, Hotel, Hotel.name == "Coral Bay Resort") == 1


# ---------- --reset
def test_reset_removes_only_seed_data(db, manager, customer):
    own_hotel = make_hotel(db, name="Мій готель", resort_en="Antalya")
    own_tour = make_tour(db, manager, hotel_id=own_hotel.id)
    reused = make_hotel(db, name="Coral Bay Resort", resort_en="Hurghada")
    seed(db)
    tours = _seed_tours(db)
    booked = next(t for t in tours if t.title_uk.startswith("Дубай") and t.seats_total > 1)
    make_order(db, customer, booked)

    result = reset(db)
    assert result.deleted == {"tours": 24, "hotels": 8, "resorts": 2, "promo_codes": 2}
    # The booked tour stays (archived), and so does its hotel.
    assert db.get(Tour, booked.id).status == TourStatus.ARCHIVED
    assert db.scalar(select(Hotel).where(Hotel.name == "Dubai Marina Skyline")) is not None
    assert any("archived" in line for line in result.kept)
    # Data the seed did not create is untouched.
    assert db.get(Tour, own_tour.id) is not None
    assert db.get(Hotel, own_hotel.id) is not None
    assert db.get(Hotel, reused.id) is not None
    assert _count(db, Resort, Resort.name_uk == "Аланія") == 1

    second = reset(db)
    assert second.deleted == {"tours": 0, "hotels": 0, "resorts": 0, "promo_codes": 0}
    # Seeding again after a reset works; the kept tour is not duplicated.
    again = seed(db)
    assert again.tours == 24 and again.hotels == 8
    assert _count(db, Tour, Tour.title_uk == booked.title_uk) == 1


def test_reset_keeps_used_promo_code(db, customer):
    seed(db)
    promo = db.scalar(select(PromoCode).where(PromoCode.code == "DEMO10"))
    tour = next(t for t in _seed_tours(db) if t.status == TourStatus.ACTIVE)
    make_order(db, customer, tour, promo_code_id=promo.id)
    reset(db)
    promo = db.scalar(select(PromoCode).where(PromoCode.code == "DEMO10"))
    assert promo is not None and promo.is_active is False
    assert _count(db, PromoCode, PromoCode.code == "DEMO1500") == 0


def test_reset_without_seed_does_nothing(db, manager):
    make_tour(db, manager)
    result = reset(db)
    assert result.deleted == {"tours": 0, "hotels": 0, "resorts": 0, "promo_codes": 0}
    assert _count(db, Tour) == 1


# ---------- --remove-legacy
def test_remove_legacy_deletes_unused_and_archives_used(db, manager, customer):
    hotels = {name: make_hotel(db, name=name, resort_en=resort_en) for resort_en, name in LEGACY_HOTELS}
    used = make_tour(db, manager, hotel_id=hotels["Akra Kemer"].id, title_en=LEGACY_TOURS[1])
    free = make_tour(db, manager, hotel_id=hotels["Rixos Downtown Antalya"].id, title_en=LEGACY_TOURS[0])
    free_id = free.id
    make_order(db, customer, used)
    other = make_tour(db, manager, title_en="Something else")

    result = remove_legacy(db)
    assert result.deleted["tours"] == 1 and result.deleted["hotels"] == 4
    assert db.get(Tour, free_id) is None
    assert db.get(Tour, used.id).status == TourStatus.ARCHIVED
    assert db.get(Hotel, hotels["Akra Kemer"].id).is_archived
    assert db.get(Tour, other.id) is not None
