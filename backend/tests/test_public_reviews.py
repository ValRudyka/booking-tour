"""Public reviews (no login): published only, author per name_display, no personal data,
photos of unpublished reviews hidden; review numbers on the tour page."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import settings
from app.models import ReviewPhoto
from app.models.enums import NameDisplay, OrderStatus, ReviewStatus, TourStatus
from tests.factories import (headers_for, make_active_tour, make_hotel, make_paid_order, make_review,
                             make_tour, make_user)

NOW = datetime.now(timezone.utc)
JPG = b"\xff\xd8\xff\xe0" + b"0" * 100


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


def review(db, author, tour, status=ReviewStatus.PUBLISHED, minutes_ago=0, **fields):
    order = make_paid_order(db, author, tour, status=OrderStatus.COMPLETED)
    item = make_review(db, order, status=status, **fields)
    if item.moderated_at:
        item.moderated_at = NOW - timedelta(minutes=minutes_ago)
        db.flush()
    return item


def with_photo(db, item) -> ReviewPhoto:
    path = f"private/reviews/{item.id}/photo.jpg"
    target = Path(settings.upload_dir) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(JPG)
    photo = ReviewPhoto(review_id=item.id, file_path=path)
    db.add(photo)
    db.flush()
    return photo


def test_only_published_newest_first_with_pages(client, db, customer, tour):
    old = review(db, customer, tour, minutes_ago=60, positive="Старий")
    new = review(db, customer, tour, minutes_ago=1, positive="Новий")
    review(db, customer, tour, status=ReviewStatus.PENDING)
    review(db, customer, tour, status=ReviewStatus.REJECTED)
    body = client.get(f"/api/tours/{tour.id}/reviews").json()
    assert body["total"] == 2 and [r["id"] for r in body["items"]] == [new.id, old.id]
    page2 = client.get(f"/api/tours/{tour.id}/reviews", params={"page": 2, "page_size": 1}).json()
    assert [r["id"] for r in page2["items"]] == [old.id]
    hotel = client.get(f"/api/hotels/{tour.hotel_id}/reviews").json()
    assert hotel["total"] == 2 and hotel["items"][0]["hotel_name"] == "Test Hotel"


def test_hotel_reviews_cover_all_its_tours(client, db, customer, manager, tour):
    same_hotel = make_active_tour(db, manager, hotel_id=tour.hotel_id, title_uk="Інший тур")
    other_hotel = make_active_tour(db, manager, hotel_id=make_hotel(db, name="Other").id)
    review(db, customer, tour)
    review(db, customer, same_hotel)
    review(db, customer, other_hotel)
    assert client.get(f"/api/hotels/{tour.hotel_id}/reviews").json()["total"] == 2
    assert client.get(f"/api/tours/{same_hotel.id}/reviews").json()["total"] == 1


def test_author_name_display(client, db, tour):
    author = make_user(db)
    author.first_name, author.last_name = "Олена", "Коваль"
    for display in (NameDisplay.FULL, NameDisplay.SHORT, NameDisplay.ANONYMOUS):
        review(db, author, tour, name_display=display)
    names = {r["author"] for r in client.get(f"/api/tours/{tour.id}/reviews").json()["items"]}
    assert names == {"Олена Коваль", "Олена К.", "Анонімний мандрівник"}


def test_no_personal_data(client, db, customer, tour):
    item = review(db, customer, tour, name_display=NameDisplay.ANONYMOUS, positive="Добре")
    with_photo(db, item)
    raw = client.get(f"/api/tours/{tour.id}/reviews").text
    data = json.loads(raw)["items"][0]
    assert set(data) == {"id", "author", "hotel_rating", "service_rating", "positive", "negative",
                         "photos", "tour_id", "tour_title_uk", "hotel_name", "trip_month", "published_at"}
    for secret in (customer.phone, customer.email, item.order.number, customer.last_name,
                   customer.first_name, f'"user_id"', f'"order_id"'):
        assert secret not in raw
    assert data["trip_month"] == item.order.start_date.strftime("%Y-%m")


def test_draft_tour_and_unknown_hotel(client, db, manager):
    draft = make_tour(db, manager, status=TourStatus.DRAFT)
    assert client.get(f"/api/tours/{draft.id}/reviews").status_code == 404
    assert client.get("/api/tours/999999/reviews").status_code == 404
    assert client.get("/api/hotels/999999/reviews").status_code == 404
    archived = make_tour(db, manager, status=TourStatus.ARCHIVED)
    assert client.get(f"/api/tours/{archived.id}/reviews").status_code == 200


def test_photo_access(client, db, customer, customer_headers, manager_headers, tour):
    published = with_photo(db, review(db, customer, tour))
    url = f"/api/reviews/{published.review_id}/photos/{published.id}"
    guest = client.get(url)
    assert guest.status_code == 200 and guest.content == JPG
    assert guest.headers["cache-control"] == "public, max-age=86400"
    assert guest.headers["content-type"] == "image/jpeg"

    for status in (ReviewStatus.PENDING, ReviewStatus.REJECTED):
        hidden = with_photo(db, review(db, customer, tour, status=status))
        url = f"/api/reviews/{hidden.review_id}/photos/{hidden.id}"
        assert client.get(url).status_code == 404                                    # guest
        assert client.get(url, headers=headers_for(make_user(db))).status_code == 404  # other client
        assert client.get(url, headers={"Authorization": "Bearer broken"}).status_code == 404
        assert client.get(url, headers=customer_headers).status_code == 200          # the author
        assert client.get(url, headers=manager_headers).status_code == 200          # moderator


def test_tour_page_shows_review_numbers(client, db, customer, tour):
    page = client.get(f"/api/tours/{tour.id}").json()
    assert (page["reviews_count"], page["service_rating_avg"], page["hotel"]["rating_avg"]) == (0, None, None)
    review(db, customer, tour, service_rating=5, hotel_rating=4)
    review(db, customer, tour, service_rating=4, hotel_rating=4)
    review(db, customer, tour, status=ReviewStatus.PENDING, service_rating=1)
    from app.services.reviews import recalc_hotel_rating

    recalc_hotel_rating(db, tour.hotel_id)
    page = client.get(f"/api/tours/{tour.id}").json()
    assert (page["reviews_count"], page["service_rating_avg"], page["hotel"]["rating_avg"]) == (2, "4.50", "4.00")
    assert Decimal(page["service_rating_avg"]) == Decimal("4.5")
