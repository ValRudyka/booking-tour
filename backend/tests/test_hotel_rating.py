"""hotels.rating_avg = average hotel_rating of published reviews (2 places, NULL without any),
recalculated in the same transaction as publish / unpublish; the catalog sorts by it."""
from decimal import Decimal

import pytest

from app.models import Hotel
from app.models.enums import OrderStatus, ReviewStatus
from app.services.reviews import recalc_hotel_rating
from tests.factories import make_active_tour, make_hotel, make_paid_order, make_review

URL = "/api/manager/reviews"


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


def review(db, customer, tour, rating, status=ReviewStatus.PENDING):
    return make_review(db, make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED),
                       status=status, hotel_rating=rating)


def rating(db, hotel_id):
    db.expire_all()
    return db.get(Hotel, hotel_id).rating_avg


def test_average_follows_publish_and_unpublish(client, db, customer, manager_headers, tour):
    five, four, four_again = (review(db, customer, tour, r) for r in (5, 4, 4))
    assert rating(db, tour.hotel_id) is None
    client.post(f"{URL}/{five.id}/publish", headers=manager_headers)
    assert rating(db, tour.hotel_id) == Decimal("5.00")
    client.post(f"{URL}/{four.id}/publish", headers=manager_headers)
    assert rating(db, tour.hotel_id) == Decimal("4.50")
    client.post(f"{URL}/{four_again.id}/publish", headers=manager_headers)
    assert rating(db, tour.hotel_id) == Decimal("4.33")                      # 13 / 3, 2 places

    for item in (five, four):                                                 # unpublish
        client.post(f"{URL}/{item.id}/reject", json={"reject_reason": "Скарга"}, headers=manager_headers)
    assert rating(db, tour.hotel_id) == Decimal("4.00")
    client.post(f"{URL}/{four_again.id}/reject", json={"reject_reason": "Скарга"}, headers=manager_headers)
    assert rating(db, tour.hotel_id) is None                                  # none published


def test_only_published_reviews_of_this_hotel_count(db, customer, manager, tour):
    other = make_active_tour(db, manager, hotel_id=make_hotel(db, name="Other").id)
    review(db, customer, tour, 2, ReviewStatus.PUBLISHED)
    review(db, customer, tour, 5, ReviewStatus.PENDING)
    review(db, customer, tour, 5, ReviewStatus.REJECTED)
    review(db, customer, other, 5, ReviewStatus.PUBLISHED)
    assert recalc_hotel_rating(db, tour.hotel_id) == Decimal("2.00")
    assert recalc_hotel_rating(db, other.hotel_id) == Decimal("5.00")


def test_rounding_half_up(db, customer, tour):
    tour.seats_total = 100                                                    # 13 paid orders
    for value in (5, 5, 4, 4, 4, 4, 4, 4):                                   # 34 / 8 = 4.25
        review(db, customer, tour, value, ReviewStatus.PUBLISHED)
    assert recalc_hotel_rating(db, tour.hotel_id) == Decimal("4.25")
    review(db, customer, tour, 5, ReviewStatus.PUBLISHED)                      # 39 / 9 = 4.333…
    assert recalc_hotel_rating(db, tour.hotel_id) == Decimal("4.33")
    for _ in range(3):
        review(db, customer, tour, 5, ReviewStatus.PUBLISHED)                  # 54 / 12 = 4.5
    review(db, customer, tour, 4, ReviewStatus.PUBLISHED)                      # 58 / 13 = 4.4615…
    assert recalc_hotel_rating(db, tour.hotel_id) == Decimal("4.46")


def test_review_keeps_its_hotel_when_the_tour_changes(client, db, customer, manager_headers, tour):
    first_hotel = tour.hotel_id
    item = review(db, customer, tour, 3)
    tour.hotel_id = make_hotel(db, name="New hotel").id          # tour edited later
    db.flush()
    client.post(f"{URL}/{item.id}/publish", headers=manager_headers)
    assert rating(db, first_hotel) == Decimal("3.00")
    assert rating(db, tour.hotel_id) is None


def test_catalog_sort_by_rating(client, db, customer, manager, manager_headers, tour):
    best = make_active_tour(db, manager, hotel_id=make_hotel(db, name="Best").id)
    unrated = make_active_tour(db, manager, hotel_id=make_hotel(db, name="Unrated").id)
    client.post(f"{URL}/{review(db, customer, tour, 3).id}/publish", headers=manager_headers)
    client.post(f"{URL}/{review(db, customer, best, 5).id}/publish", headers=manager_headers)
    items = client.get("/api/tours", params={"sort": "rating_desc"}).json()["items"]
    order = [i["id"] for i in items if i["id"] in (tour.id, best.id, unrated.id)]
    assert order == [best.id, tour.id, unrated.id]                            # NULL last
    assert [i["hotel"]["rating_avg"] for i in items if i["id"] in (best.id, tour.id)] == ["5.00", "3.00"]
