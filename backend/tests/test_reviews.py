"""Client reviews (ТЗ 4.5.7, form 4.6.1.4): who may write one, validation, private photos,
the one allowed resubmission, pre-moderation setting."""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Hotel, OrderStatusHistory, Review, ReviewPhoto, Setting
from app.models.enums import OrderStatus, ReviewStatus, UserRole
from tests.factories import headers_for, make_active_tour, make_paid_order, make_user

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
PDF = b"%PDF-1.4\n" + b"0" * 200


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


@pytest.fixture()
def order(db, customer, tour):
    return make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED)


def write(client, headers, order_id, hotel="5", service="4", photos=None, **fields):
    data = {"hotel_rating": hotel, "service_rating": service, **fields}
    return client.post(f"/api/orders/{order_id}/review", data=data, files=photos, headers=headers)


def photos(*items):
    return [("photos", item) for item in items]


# ---------- who may write
def test_review_of_a_completed_trip(client, db, customer, customer_headers, tour, order):
    response = write(client, customer_headers, order.id, positive=" Чисте море ", negative="",
                     name_display="full", photos=photos(("beach.jpg", JPG, "image/jpeg"),
                                                         ("pool.png", PNG, "image/png")))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["hotel_rating"], body["service_rating"], body["positive"],
            body["negative"], body["author"], body["can_resubmit"]) == (
        "pending", 5, 4, "Чисте море", None, "Тарас Шевченко", False)
    review = db.get(Review, body["id"])
    assert review.hotel_id == tour.hotel_id and review.user_id == customer.id
    assert db.get(Hotel, tour.hotel_id).rating_avg is None        # not published yet
    assert len(body["photos"]) == 2
    assert body["photos"][0]["url"] == f"/api/reviews/{review.id}/photos/{body['photos'][0]['id']}"


def test_texts_are_optional(client, customer_headers, order):
    response = write(client, customer_headers, order.id)
    assert response.status_code == 201
    assert (response.json()["positive"], response.json()["negative"], response.json()["author"]) == (
        None, None, "Тарас Ш.")                                    # short name by default


def test_archived_only_after_completion(client, db, customer, customer_headers, tour):
    finished = make_paid_order(db, customer, tour, status=OrderStatus.ARCHIVED)
    db.add(OrderStatusHistory(order_id=finished.id, old_status="documents_ready", new_status="completed"))
    db.flush()
    assert write(client, customer_headers, finished.id).status_code == 201
    rejected = make_paid_order(db, customer, tour, status=OrderStatus.ARCHIVED)
    db.add(OrderStatusHistory(order_id=rejected.id, old_status="in_progress", new_status="rejected"))
    db.flush()
    response = write(client, customer_headers, rejected.id)
    assert response.status_code == 409 and "після завершення подорожі" in response.json()["detail"]


@pytest.mark.parametrize("status", [OrderStatus.PAID, OrderStatus.CONFIRMED, OrderStatus.DOCUMENTS_READY,
                                    OrderStatus.CANCELLED, OrderStatus.REJECTED])
def test_not_before_the_trip(client, db, customer, customer_headers, tour, status):
    order = make_paid_order(db, customer, tour, status=status)
    assert write(client, customer_headers, order.id).status_code == 409


def test_one_review_per_order_and_own_orders_only(client, db, customer_headers, order):
    assert write(client, customer_headers, order.id).status_code == 201
    second = write(client, customer_headers, order.id)
    assert second.status_code == 409 and "вже залишено" in second.json()["detail"]
    assert write(client, headers_for(make_user(db)), order.id).status_code == 404
    assert write(client, {}, order.id).status_code == 401
    for role in (UserRole.MANAGER, UserRole.FINANCE):
        assert write(client, headers_for(make_user(db, role=role)), order.id).status_code == 403


# ---------- validation
@pytest.mark.parametrize("hotel, service", [("0", "5"), ("6", "5"), ("5", "0"), ("5", "9")])
def test_ratings_range(client, customer_headers, order, hotel, service):
    response = write(client, customer_headers, order.id, hotel=hotel, service=service)
    assert response.status_code == 422 and "від 1 до 5" in response.json()["detail"]


def test_missing_rating_and_long_text(client, customer_headers, order):
    assert client.post(f"/api/orders/{order.id}/review", data={"hotel_rating": "5"},
                       headers=customer_headers).status_code == 422
    assert write(client, customer_headers, order.id, positive="x" * 2001).status_code == 422
    assert write(client, customer_headers, order.id, name_display="nickname").status_code == 422


def stored_photo_files() -> int:
    folder = Path(settings.upload_dir) / "private" / "reviews"
    return sum(p.is_file() for p in folder.rglob("*")) if folder.exists() else 0


def test_photo_type_size_and_count(client, db, customer_headers, order, monkeypatch):
    before = stored_photo_files()
    wrong = write(client, customer_headers, order.id,
                  photos=photos(("ok.jpg", JPG, "image/jpeg"), ("fake.jpg", PDF, "image/jpeg")))
    assert wrong.status_code == 422 and "fake.jpg" in wrong.json()["detail"]
    assert db.scalar(select(Review).where(Review.order_id == order.id)) is None   # nothing kept
    assert stored_photo_files() == before                                        # no orphan files

    monkeypatch.setattr(settings, "max_review_photo_mb", 0)
    assert write(client, customer_headers, order.id,
                 photos=photos(("big.jpg", JPG, "image/jpeg"))).status_code == 413
    monkeypatch.setattr(settings, "max_review_photo_mb", 5)
    too_many = write(client, customer_headers, order.id,
                     photos=photos(*[(f"{i}.jpg", JPG, "image/jpeg") for i in range(11)]))
    assert too_many.status_code == 422 and "10 фото" in too_many.json()["detail"]
    ten = write(client, customer_headers, order.id,
                photos=photos(*[(f"{i}.jpg", JPG, "image/jpeg") for i in range(10)]))
    assert ten.status_code == 201 and len(ten.json()["photos"]) == 10


def test_photos_are_private(client, db, customer_headers, manager_headers, order):
    body = write(client, customer_headers, order.id, photos=photos(("a.jpg", JPG, "image/jpeg"))).json()
    photo = db.get(ReviewPhoto, body["photos"][0]["id"])
    assert photo.file_path.startswith(f"private/reviews/{body['id']}/") and photo.file_path.endswith(".jpg")
    assert client.get(f"/uploads/{photo.file_path}").status_code == 404
    url = body["photos"][0]["url"]
    assert client.get(url).status_code == 404                                    # guest, pending
    assert client.get(url, headers=headers_for(make_user(db))).status_code == 404  # another client
    own = client.get(url, headers=customer_headers)
    assert own.status_code == 200 and own.content == JPG and own.headers["cache-control"] == "private, no-store"
    assert client.get(url, headers=manager_headers).status_code == 200
    assert client.get(f"/api/reviews/{body['id'] + 1}/photos/{photo.id}").status_code == 404


# ---------- my reviews and the one resubmission
def test_my_reviews_and_resubmission(client, db, customer, customer_headers, tour, order):
    created = write(client, customer_headers, order.id, positive="Добре",
                    photos=photos(("old.jpg", JPG, "image/jpeg"))).json()
    review = db.get(Review, created["id"])
    old_file = Path(settings.upload_dir) / review.photos[0].file_path

    early = client.patch(f"/api/me/reviews/{review.id}", data={"positive": "x"}, headers=customer_headers)
    assert early.status_code == 409 and "відхилений" in early.json()["detail"]

    review.status, review.reject_reason = ReviewStatus.REJECTED, "Нецензурна лексика"
    db.flush()
    mine = client.get("/api/me/reviews", headers=customer_headers).json()
    assert mine["total"] == 1
    assert (mine["items"][0]["status"], mine["items"][0]["reject_reason"], mine["items"][0]["can_resubmit"]) == (
        "rejected", "Нецензурна лексика", True)

    fixed = client.patch(f"/api/me/reviews/{review.id}", data={"positive": "Чудовий готель", "hotel_rating": "4"},
                         files=photos(("new.png", PNG, "image/png")), headers=customer_headers)
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert (body["status"], body["reject_reason"], body["positive"], body["hotel_rating"],
            body["service_rating"], body["can_resubmit"]) == ("pending", None, "Чудовий готель", 4, 4, False)
    assert len(body["photos"]) == 1 and body["photos"][0]["id"] != created["photos"][0]["id"]
    assert not old_file.exists()                                  # replaced photo removed

    review = db.get(Review, review.id)
    assert review.resubmitted_at is not None and review.submitted_at == review.resubmitted_at
    review.status = ReviewStatus.REJECTED
    db.flush()
    again = client.patch(f"/api/me/reviews/{review.id}", data={"positive": "x"}, headers=customer_headers)
    assert again.status_code == 409 and "один раз" in again.json()["detail"]
    assert client.get("/api/me/reviews", headers=customer_headers).json()["items"][0]["can_resubmit"] is False


def test_resubmit_validation_and_privacy(client, db, customer_headers, order):
    created = write(client, customer_headers, order.id).json()
    review = db.get(Review, created["id"])
    review.status = ReviewStatus.REJECTED
    db.flush()
    assert client.patch(f"/api/me/reviews/{review.id}", data={"hotel_rating": "7"},
                        headers=customer_headers).status_code == 422
    assert db.get(Review, review.id).status == ReviewStatus.REJECTED              # not changed
    stranger = headers_for(make_user(db))
    assert client.patch(f"/api/me/reviews/{review.id}", data={"positive": "x"}, headers=stranger).status_code == 404
    assert client.get("/api/me/reviews", headers=stranger).json()["total"] == 0
    assert client.get("/api/me/reviews").status_code == 401


def test_without_premoderation_published_at_once(client, db, customer_headers, tour, order):
    db.get(Setting, "review_premoderation").value = False
    db.flush()
    body = write(client, customer_headers, order.id, hotel="4").json()
    assert body["status"] == "published"
    review = db.get(Review, body["id"])
    assert review.moderated_by is None and review.moderated_at is not None       # the System
    assert db.get(Hotel, tour.hotel_id).rating_avg == 4


def test_completed_notification_invites_a_review(db, customer, tour):
    from app.models import Notification
    from app.services.order_status import change_status

    order = make_paid_order(db, customer, tour, status=OrderStatus.DOCUMENTS_READY)
    change_status(db, order, OrderStatus.COMPLETED, None)
    note = db.scalars(select(Notification).where(Notification.order_id == order.id)).one()
    assert "залиште відгук" in note.body and "«Мої замовлення»" in note.body
