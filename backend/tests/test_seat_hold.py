"""Seat holds (ТЗ 4.4.1): holds reduce free seats, expired holds do not, the last seat goes to one client."""
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Hotel, Order, Tour, User
from app.models.enums import Currency, OrderStatus, TourStatus, UserRole
from app.services import orders as order_service
from app.services.errors import DomainError
from app.services import clock
from tests.factories import make_active_tour, make_hotel, make_order, make_user

NOW = datetime.now(timezone.utc)


def free_seats(client, tour_id):
    return client.get(f"/api/tours/{tour_id}").json()["free_seats"]


def test_hold_reduces_free_seats_and_expired_hold_does_not(client, db, manager):
    tour = make_active_tour(db, manager)                 # 10 seats
    customer = make_user(db)
    make_order(db, customer, tour, adults=2, children=1, hold_expires_at=NOW + timedelta(minutes=5))
    assert free_seats(client, tour.id) == 7
    make_order(db, customer, tour, adults=4, hold_expires_at=NOW - timedelta(seconds=1))
    assert free_seats(client, tour.id) == 7              # expired before the job ran
    make_order(db, customer, tour, adults=1, status=OrderStatus.CANCELLED,
               hold_expires_at=NOW + timedelta(minutes=5))
    assert free_seats(client, tour.id) == 7              # cancelled: no hold


def test_two_clients_race_for_the_last_seat(engine, monkeypatch):
    """Two transactions in two threads book the last seat at the same moment. The tour row lock
    makes the second one wait and then see 0 free seats: exactly one order is created.
    Each booking pauses after counting free seats, so without the lock both would count 1."""
    count_free_seats = order_service.free_seats

    def slow_free_seats(*args, **kwargs):
        result = count_free_seats(*args, **kwargs)
        time.sleep(0.3)
        return result

    monkeypatch.setattr(order_service, "free_seats", slow_free_seats)
    with Session(engine) as setup:                       # committed data, visible to both threads
        manager = User(phone="+380990000001", email="race-manager@test.ua", password_hash="x",
                       role=UserRole.MANAGER, last_name="Гонка", first_name="Тест")
        clients = [User(phone=f"+38099000000{i}", email=f"race{i}@test.ua", password_hash="x",
                        role=UserRole.CLIENT, last_name="Гонка", first_name="Тест") for i in (2, 3)]
        setup.add_all([manager, *clients])
        setup.flush()
        hotel = make_hotel(setup, name="Race Hotel")
        start = clock.today() + timedelta(days=10)
        tour = Tour(title_uk="Гонка", title_en="Race", hotel_id=hotel.id, transport_type="none",
                    departure_from=start, departure_to=start + timedelta(days=5), nights=3,
                    seats_total=1, base_price=Decimal("100"), currency=Currency.EUR,
                    status=TourStatus.ACTIVE, created_by=manager.id)
        setup.add(tour)
        setup.commit()
        ids = dict(tour=tour.id, hotel=hotel.id, users=[manager.id] + [c.id for c in clients])

    barrier = threading.Barrier(2)
    results: list = []

    def book(client_id: int) -> None:
        with Session(engine) as db:
            barrier.wait()                               # start both bookings together
            try:
                order_service.create_order(db, db.get(User, client_id), {
                    "tour_id": ids["tour"], "start_date": start, "adults": 1, "children": 0})
                db.commit()
                results.append("ok")
            except DomainError as error:
                db.rollback()
                results.append(error.status_code)

    try:
        threads = [threading.Thread(target=book, args=(uid,)) for uid in ids["users"][1:]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert sorted(results, key=str) == [409, "ok"]
    finally:                                             # remove the committed data again
        with Session(engine) as cleanup:
            cleanup.execute(delete(Order).where(Order.tour_id == ids["tour"]))
            cleanup.execute(delete(Tour).where(Tour.id == ids["tour"]))
            cleanup.execute(delete(Hotel).where(Hotel.id == ids["hotel"]))
            cleanup.execute(delete(User).where(User.id.in_(ids["users"])))
            cleanup.commit()
