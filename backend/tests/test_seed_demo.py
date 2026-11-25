"""Demo seed (scripts.seed_demo): dev guard, the catalog it builds (hotel facts, meal plans, lists,
generated photos, past trips with reviews), idempotency, --reset safety."""
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import (AuditLog, Hotel, Notification, Order, OrderStatusHistory, Payment, PromoCode,
                        Resort, Review, ReviewPhoto, Tour, TourImage)
from app.models.enums import OrderStatus, PaymentOrigin, ReviewStatus, TourStatus
from app.services import clock
from app.services.images import detect_extension
from scripts import complete_orders, seed_demo
from scripts.placeholder_images import scene_png
from scripts.seed_demo import (LEGACY_HOTELS, LEGACY_TOURS, TOUR_PHOTOS, load_hotels,
                               load_list_defaults, load_tours, remove_legacy, reset, seed,
                               seed_accounts, seed_clients)
from tests.factories import make_hotel, make_order, make_tour

UPLOADS = Path(settings.upload_dir)
ALL_TOURS, LISTED, PAST_TRIPS, REVIEW_PHOTOS = 28, 25, 9, 7
FULL_CHAIN = ["checkout", "awaiting_payment", "paid", "in_progress", "confirmed", "documents_ready",
              "completed"]


def _count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def _seed_tours(db):
    _admin, manager = seed_accounts(db, create=False)
    return db.scalars(select(Tour).where(Tour.created_by == manager.id).order_by(Tour.id)).all()


def _demo_orders(db):
    ids = [c.id for c in seed_clients(db, create=False) if c is not None]
    return db.scalars(select(Order).where(Order.client_id.in_(ids)).order_by(Order.id)).all()


def _files(folder: str) -> list[Path]:
    root = UPLOADS / folder
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# ---------- data files
def test_data_files_are_consistent():
    hotels, tours, defaults = load_hotels(), load_tours(), load_list_defaults()
    keys = [h["key"] for h in hotels]
    assert len(hotels) == 10 and len(set(keys)) == 10
    assert {h["meal_plan"] for h in hotels} <= {"UAI", "AI", "HB", "BB"}
    for h in hotels:   # the facts that now have their own columns
        assert 1 <= h["beach_line"] <= 5 and h["distance_to_beach_m"] >= 0
        assert time.fromisoformat(h["check_in"]) and time.fromisoformat(h["check_out"])
        assert h["amenities"] and h["room_types"]
    assert len(tours) == ALL_TOURS and len({t["title"] for t in tours}) == ALL_TOURS
    for key in keys:
        assert 2 <= sum(t["hotel"] == key for t in tours) <= 3
    for t in tours:
        assert t["hotel"] in keys
        assert 3 <= len(t["program"]) <= 5 and 5 <= t["nights"] <= 14
        if t.get("past_trips"):        # a long season that started in the past and still sells
            assert t["start_in"] < 0 < t["start_in"] + t["span"] - 1 and t["status"] == "active"
            for trip in t["past_trips"]:
                assert trip["start_offset"] + t["nights"] < -t["start_in"]   # the trip is over
                assert 1 <= trip["client"] <= 4
        else:
            assert 20 <= t["start_in"] <= 182
    assert sum(len(t.get("past_trips", [])) for t in tours) == PAST_TRIPS
    assert [t["status"] for t in tours].count("draft") == 2
    assert [t["status"] for t in tours].count("archived") == 1
    # Insurance and transfer are paid at checkout, so they are never «included».
    for kind in ("air", "bus", "none"):
        assert not any("страхування" in line.lower() or "трансфер" in line.lower()
                       for line in defaults["included"][kind])


def test_placeholder_photos_are_valid_pngs():
    data = scene_png(7)
    assert detect_extension(data[:64]) == "png"
    assert len(data) < 1024 * 1024 and scene_png(7) == data and scene_png(8) != data


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
    assert (result.resorts, result.hotels, result.tours, result.promo_codes) == (2, 10, ALL_TOURS, 2)
    assert result.tour_photos == ALL_TOURS * TOUR_PHOTOS

    tours = _seed_tours(db)
    statuses = [t.status for t in tours]
    assert statuses.count(TourStatus.ACTIVE) == LISTED
    assert statuses.count(TourStatus.DRAFT) == 2
    assert statuses.count(TourStatus.ARCHIVED) == 1
    assert sum(t.is_featured for t in tours) == 6
    assert all(t.title_en == t.title_uk for t in tours)                # Ukrainian only
    assert all(3 <= len(t.program_days) <= 5 for t in tours)
    assert all(len(t.images) == TOUR_PHOTOS for t in tours)
    assert all(t.meal_plan is not None and t.included and t.excluded for t in tours)

    # Missing resorts went through the admin service (audit row by the seed admin);
    # Аланія is the migrated seeded resort, not a new one.
    admin, manager = seed_accounts(db, create=False)
    assert not admin.is_active
    for name in ("Салоу", "Золоті Піски"):
        resort = db.scalar(select(Resort).where(Resort.name_uk == name))
        assert _count(db, AuditLog, AuditLog.user_id == admin.id, AuditLog.entity == "resort",
                      AuditLog.entity_id == str(resort.id), AuditLog.action == "created") == 1
    assert _count(db, Resort, Resort.name_uk == "Аланія") == 1
    assert _count(db, Resort, Resort.name_uk == "Аланья") == 0

    # Hotel facts are columns now; the description is only the description.
    hotel = db.scalar(select(Hotel).where(Hotel.name == "Alanya Blue Coast"))
    source = next(h for h in load_hotels() if h["name"] == "Alanya Blue Coast")
    assert hotel.resort.name_uk == "Аланія"
    assert hotel.description == source["description"]
    assert (hotel.beach_line, hotel.distance_to_beach_m, hotel.check_out) == (2, 150, time(11, 0))
    assert hotel.room_types == ["Стандартний номер", "Номер з балконом"]
    alanya_tours = [t for t in tours if t.hotel_id == hotel.id]
    assert {t.meal_plan.value for t in alanya_tours} == {"hb"}             # the hotel's board

    # Photos: generated files, each marked as the seed's own, served publicly.
    image = tours[0].images[0]
    assert _count(db, AuditLog, AuditLog.user_id == manager.id, AuditLog.entity == "tour_image",
                  AuditLog.action == "created") == ALL_TOURS * TOUR_PHOTOS
    served = client.get(f"/uploads/{image.file_path}")
    assert served.status_code == 200 and served.content[:8] == b"\x89PNG\r\n\x1a\n"

    cards = []
    for page in (1, 2, 3):
        body = client.get("/api/tours", params={"page_size": 12, "page": page}).json()
        assert body["total"] == LISTED
        cards += body["items"]
    assert len(cards) == LISTED and all(c["image_url"] for c in cards)
    assert [c["free_seats"] for c in cards].count(1) == 1
    assert client.get("/api/tours", params={"featured": True}).json()["total"] == 6


def test_seed_adds_past_trips_with_published_reviews(client, db):
    result = seed(db)
    assert (result.orders, result.reviews) == (PAST_TRIPS, PAST_TRIPS)

    orders = _demo_orders(db)
    assert len(orders) == PAST_TRIPS
    for order in orders:
        assert order.status == OrderStatus.COMPLETED and order.end_date < clock.today()
        assert [h.new_status for h in order.history] == FULL_CHAIN
        assert [h.changed_at for h in order.history] == sorted(h.changed_at for h in order.history)
        assert order.created_at.date() < order.start_date                   # backdated
        assert order.tour.departure_from <= order.start_date <= order.tour.departure_to
        assert len(order.tourists) == order.adults == 2
        payment = order.payments[0]
        assert (payment.origin, payment.paid_amount) == (PaymentOrigin.DEMO_SEED, order.total_uah)
    for order in orders:
        assert order.tour.seats_sold == 6                                    # 3 trips x 2 tourists

    reviews = db.scalars(select(Review).order_by(Review.id)).all()
    assert len(reviews) == PAST_TRIPS and {r.status for r in reviews} == {ReviewStatus.PUBLISHED}
    assert _count(db, ReviewPhoto) == REVIEW_PHOTOS
    ratings = {h.name: h.rating_avg for h in db.scalars(select(Hotel).where(Hotel.rating_avg.is_not(None)))}
    assert ratings == {"Sinai Garden Hotel": Decimal("4.33"), "Dubai Marina Skyline": Decimal("4.67"),
                       "Alanya Blue Coast": Decimal("3.33")}

    # Public tour reviews, and a guest can open a published review's photo.
    tour = next(o.tour for o in orders if o.tour.hotel.name == "Sinai Garden Hotel")
    page = client.get(f"/api/tours/{tour.id}/reviews").json()
    assert page["total"] == 3
    photo_url = next(r["photos"][0]["url"] for r in page["items"] if r["photos"])
    photo = client.get(photo_url)
    assert photo.status_code == 200 and photo.headers["cache-control"].startswith("public")

    # The finance register tells demo money from real money.
    finance_headers = _finance_headers(db)
    demo = client.get("/api/finance/payments", headers=finance_headers,
                      params={"origin": "demo_seed", "page_size": 50}).json()
    assert demo["total"] == PAST_TRIPS and {p["origin"] for p in demo["items"]} == {"demo_seed"}
    real = client.get("/api/finance/payments", headers=finance_headers, params={"origin": "app"}).json()
    assert real["total"] == 0


def _finance_headers(db):
    from app.models.enums import UserRole
    from tests.factories import headers_for, make_user

    return headers_for(make_user(db, role=UserRole.FINANCE))


def test_seed_is_idempotent(db):
    seed(db)
    again = seed(db)
    assert (again.resorts, again.hotels, again.tours, again.tour_photos, again.promo_codes,
            again.orders, again.reviews) == (0, 0, 0, 0, 0, 0, 0)
    assert _count(db, Hotel) == 10
    assert _count(db, Tour) == ALL_TOURS
    assert _count(db, TourImage) == ALL_TOURS * TOUR_PHOTOS
    assert _count(db, PromoCode) == 2
    assert len(_demo_orders(db)) == PAST_TRIPS and _count(db, Review) == PAST_TRIPS


def test_seed_reuses_an_existing_hotel(db):
    own = make_hotel(db, name="Coral Bay Resort", resort_en="Hurghada", description="Мій опис")
    assert seed(db).hotels == 9
    assert db.get(Hotel, own.id).description == "Мій опис"   # reused, not changed
    assert db.get(Hotel, own.id).amenities == []
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
    tour_files, review_files = len(_files("tours")), len(_files("private/reviews"))
    assert tour_files >= ALL_TOURS * TOUR_PHOTOS and review_files >= REVIEW_PHOTOS

    result = reset(db)
    assert result.deleted == {"orders": PAST_TRIPS, "reviews": PAST_TRIPS,
                              "tour_photos": ALL_TOURS * TOUR_PHOTOS, "tours": ALL_TOURS - 1,
                              "hotels": 8, "resorts": 2, "promo_codes": 2}
    # The booked tour stays (archived, without the seed's photos), and so does its hotel.
    assert db.get(Tour, booked.id).status == TourStatus.ARCHIVED
    assert _count(db, TourImage, TourImage.tour_id == booked.id) == 0
    assert db.scalar(select(Hotel).where(Hotel.name == "Dubai Marina Skyline")) is not None
    assert any("archived" in line for line in result.kept)
    # Demo trips are gone with their money rows, notifications and files; ratings recalculated.
    assert _demo_orders(db) == [] and _count(db, Review) == 0
    assert _count(db, Payment, Payment.origin == PaymentOrigin.DEMO_SEED) == 0
    client_ids = [c.id for c in seed_clients(db, create=False)]
    assert _count(db, Notification, Notification.user_id.in_(client_ids)) == 0
    assert len(_files("tours")) == tour_files - ALL_TOURS * TOUR_PHOTOS
    assert len(_files("private/reviews")) == review_files - REVIEW_PHOTOS
    assert db.scalar(select(Hotel.rating_avg).where(Hotel.name == "Dubai Marina Skyline")) is None
    assert _count(db, AuditLog, AuditLog.entity == "order", AuditLog.action == "deleted") == PAST_TRIPS
    # Data the seed did not create is untouched.
    assert db.get(Tour, own_tour.id) is not None
    assert db.get(Hotel, own_hotel.id) is not None
    assert db.get(Hotel, reused.id) is not None
    assert _count(db, Resort, Resort.name_uk == "Аланія") == 1

    second = reset(db)
    assert set(second.deleted.values()) == {0}
    # Seeding again after a reset works; the kept tour is not duplicated.
    again = seed(db)
    assert again.tours == ALL_TOURS - 1 and again.hotels == 8 and again.orders == PAST_TRIPS
    assert _count(db, Tour, Tour.title_uk == booked.title_uk) == 1


def test_reset_gives_back_the_seats_of_a_tour_that_stays(db, customer):
    """A real client also ordered a long-season tour with demo trips: the tour is archived, not
    deleted, its demo orders go and seats_sold drops by their tourists; the real order stays."""
    seed(db)
    tour = next(o.tour for o in _demo_orders(db) if o.tour.hotel.name == "Sinai Garden Hotel")
    assert tour.seats_sold == 6
    real = make_order(db, customer, tour, status=OrderStatus.PAID, start_date=tour.departure_to,
                      end_date=tour.departure_to + timedelta(days=tour.nights))
    tour.seats_sold += 2
    db.flush()

    reset(db)
    db.refresh(tour)
    assert tour.status == TourStatus.ARCHIVED and tour.seats_sold == 2
    assert db.get(Order, real.id) is not None
    assert _count(db, OrderStatusHistory, OrderStatusHistory.order_id == real.id) == 0   # untouched


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
    assert set(result.deleted.values()) == {0}
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
