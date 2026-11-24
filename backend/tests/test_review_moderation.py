"""Moderation of reviews by managers: queue, publish, reject / unpublish, notifications."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification, Review, ReviewPhoto
from app.models.enums import OrderStatus, ReviewStatus, UserRole
from tests.factories import (headers_for, make_active_tour, make_hotel, make_paid_order, make_review,
                             make_user)

URL = "/api/manager/reviews"
NOW = datetime.now(timezone.utc)


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


def pending_review(db, customer, tour, minutes_ago=0, **fields):
    order = make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED)
    review = make_review(db, order, status=ReviewStatus.PENDING, **fields)
    review.submitted_at = NOW - timedelta(minutes=minutes_ago)
    db.flush()
    return review


def notes(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id)).all()


def test_queue_oldest_first_and_filters(client, db, customer, manager, manager_headers, tour):
    other_tour = make_active_tour(db, manager, hotel_id=make_hotel(db, name="Other").id)
    newer = pending_review(db, customer, tour, minutes_ago=5)
    older = pending_review(db, customer, tour, minutes_ago=60)
    elsewhere = pending_review(db, customer, other_tour, minutes_ago=30)
    published = make_review(db, make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED))

    def ids(**params):
        return [r["id"] for r in client.get(URL, params=params, headers=manager_headers).json()["items"]]

    assert ids() == [older.id, elsewhere.id, newer.id]
    assert ids(tour_id=tour.id) == [older.id, newer.id]
    assert ids(hotel_id=other_tour.hotel_id) == [elsewhere.id]
    assert ids(status="published") == [published.id]
    item = client.get(URL, headers=manager_headers).json()["items"][0]
    assert item["order_number"].startswith("TU-") and item["author_full_name"] == "Шевченко Тарас"


def test_detail_with_photos(client, db, customer, manager_headers, tour):
    review = pending_review(db, customer, tour)
    db.add(ReviewPhoto(review_id=review.id, file_path=f"private/reviews/{review.id}/x.jpg"))
    db.flush()
    body = client.get(f"{URL}/{review.id}", headers=manager_headers).json()
    assert body["photos"][0]["url"].startswith(f"/api/reviews/{review.id}/photos/")
    assert client.get(f"{URL}/999999", headers=manager_headers).status_code == 404


def test_publish(client, db, customer, manager, manager_headers, tour):
    review = pending_review(db, customer, tour, hotel_rating=4)
    response = client.post(f"{URL}/{review.id}/publish", headers=manager_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["moderated_by"]) == ("published", manager.id)
    assert notes(db, customer)[-1].title == "Ваш відгук опубліковано"
    again = client.post(f"{URL}/{review.id}/publish", headers=manager_headers)
    assert again.status_code == 409 and "опубліковано" in again.json()["detail"]


def test_reject_needs_a_reason_and_tells_the_client(client, db, customer, manager_headers, tour):
    review = pending_review(db, customer, tour)
    assert client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "  "},
                       headers=manager_headers).status_code == 422
    assert client.post(f"{URL}/{review.id}/reject", json={}, headers=manager_headers).status_code == 422
    response = client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "Реклама іншого сайту"},
                           headers=manager_headers)
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    note = notes(db, customer)[-1]
    assert note.title == "Відгук не опубліковано"
    assert "Реклама іншого сайту" in note.body and "один раз виправити" in note.body
    mine = client.get("/api/me/reviews", headers=headers_for(customer)).json()["items"][0]
    assert (mine["status"], mine["reject_reason"]) == ("rejected", "Реклама іншого сайту")
    assert client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "x"},
                       headers=manager_headers).status_code == 409
    assert client.post(f"{URL}/{review.id}/publish", headers=manager_headers).status_code == 409


def test_second_rejection_has_no_resubmit_hint(client, db, customer, manager_headers, tour):
    review = pending_review(db, customer, tour)
    review.resubmitted_at = NOW
    db.flush()
    client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "Знову спам"}, headers=manager_headers)
    assert "виправити" not in notes(db, customer)[-1].body


def test_unpublish(client, db, customer, manager_headers, tour):
    review = make_review(db, make_paid_order(db, customer, tour, status=OrderStatus.COMPLETED))
    response = client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "Скарга готелю підтверджена"},
                           headers=manager_headers)
    assert response.json()["status"] == "rejected"
    assert notes(db, customer)[-1].title == "Відгук знято з публікації"


def test_staff_cannot_edit_a_review(client, db, customer, manager_headers, tour):
    review = pending_review(db, customer, tour, positive="Оригінальний текст")
    for method in (client.patch, client.put):
        assert method(f"{URL}/{review.id}", json={"positive": "Змінено"},
                      headers=manager_headers).status_code == 405
    # A manager is not the author: the client's correction endpoint is not theirs either.
    assert client.patch(f"/api/me/reviews/{review.id}", data={"positive": "Змінено"},
                        headers=manager_headers).status_code == 403
    client.post(f"{URL}/{review.id}/publish", headers=manager_headers)
    db.expire_all()
    assert db.get(Review, review.id).positive == "Оригінальний текст"


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.FINANCE, UserRole.ADMIN])
def test_moderation_only_for_managers(client, db, customer, tour, role):
    review = pending_review(db, customer, tour)
    headers = headers_for(make_user(db, role=role))
    assert client.get(URL, headers=headers).status_code == 403
    assert client.get(f"{URL}/{review.id}", headers=headers).status_code == 403
    assert client.post(f"{URL}/{review.id}/publish", headers=headers).status_code == 403
    assert client.post(f"{URL}/{review.id}/reject", json={"reject_reason": "x"}, headers=headers).status_code == 403
    assert client.get(URL).status_code == 401
    assert db.get(Review, review.id).status == ReviewStatus.PENDING
