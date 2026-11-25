"""«Обране» of the client (spec 08 §5; ТЗ 5.7, out of MVP in 2.7)."""
from datetime import timedelta

from app.models import Favorite
from app.models.enums import TourStatus, UserRole
from app.services import clock, favorites
from tests.factories import headers_for, make_active_tour, make_tour, make_user

URL = "/api/me/favorites"


def ids(client, headers):
    response = client.get(f"{URL}/ids", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_add_list_remove(client, db, manager, customer_headers):
    first = make_active_tour(db, manager)
    second = make_active_tour(db, manager)
    assert client.put(f"{URL}/{first.id}", headers=customer_headers).status_code == 204
    assert client.put(f"{URL}/{second.id}", headers=customer_headers).status_code == 204
    assert set(ids(client, headers=customer_headers)) == {first.id, second.id}

    page = client.get(URL, headers=customer_headers).json()
    assert page["total"] == 2
    card = page["items"][0]
    assert card["for_sale"] is True and card["added_at"]
    assert {"title_uk", "hotel", "price_from_uah", "free_seats", "image_url"} <= card.keys()  # a catalog card

    assert client.delete(f"{URL}/{first.id}", headers=customer_headers).status_code == 204
    assert ids(client, customer_headers) == [second.id]


def test_add_and_remove_are_idempotent(client, db, manager, customer_headers):
    tour = make_active_tour(db, manager)
    for _ in range(2):
        assert client.put(f"{URL}/{tour.id}", headers=customer_headers).status_code == 204
    assert ids(client, customer_headers) == [tour.id]
    for _ in range(2):
        assert client.delete(f"{URL}/{tour.id}", headers=customer_headers).status_code == 204
    assert ids(client, customer_headers) == []


def test_only_tours_for_sale_can_be_added(client, db, manager, customer_headers):
    draft = make_tour(db, manager, status=TourStatus.DRAFT)
    last_day = make_active_tour(db, manager, departure_from=clock.today() - timedelta(days=3),
                                departure_to=clock.today())
    for tour_id in (draft.id, last_day.id, 999999):
        response = client.put(f"{URL}/{tour_id}", headers=customer_headers)
        assert response.status_code == 404 and response.json()["detail"] == "Тур не знайдено"
    assert ids(client, customer_headers) == []


def test_a_favourite_that_left_the_catalog_stays_marked(client, db, manager, customer_headers):
    tour = make_active_tour(db, manager)
    client.put(f"{URL}/{tour.id}", headers=customer_headers)
    tour.status = TourStatus.ARCHIVED
    db.flush()
    [card] = client.get(URL, headers=customer_headers).json()["items"]
    assert (card["id"], card["for_sale"]) == (tour.id, False)


def test_lists_are_per_client(client, db, manager, customer_headers):
    tour = make_active_tour(db, manager)
    other = headers_for(make_user(db))
    client.put(f"{URL}/{tour.id}", headers=other)
    assert ids(client, customer_headers) == []
    assert client.get(URL, headers=customer_headers).json()["total"] == 0
    client.delete(f"{URL}/{tour.id}", headers=customer_headers)       # not mine: nothing happens
    assert ids(client, other) == [tour.id]


def test_newest_first_and_pages(client, db, manager, customer_headers):
    tours = [make_active_tour(db, manager) for _ in range(3)]
    for tour in tours:
        client.put(f"{URL}/{tour.id}", headers=customer_headers)
    page = client.get(URL, params={"page": 2, "page_size": 2}, headers=customer_headers).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    # One test transaction gives every row the same created_at; the tour id breaks the tie.
    assert ids(client, customer_headers) == [t.id for t in reversed(tours)]
    assert page["items"][0]["id"] == tours[0].id


def test_limit(client, db, manager, customer, customer_headers, monkeypatch):
    monkeypatch.setattr(favorites, "MAX_FAVORITES", 1)
    first, second = make_active_tour(db, manager), make_active_tour(db, manager)
    client.put(f"{URL}/{first.id}", headers=customer_headers)
    response = client.put(f"{URL}/{second.id}", headers=customer_headers)
    assert response.status_code == 422 and "не більше 1" in response.json()["detail"]
    assert client.put(f"{URL}/{first.id}", headers=customer_headers).status_code == 204   # already there


def test_clients_only(client, db, manager):
    tour = make_active_tour(db, manager)
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/{tour.id}").status_code == 401
    staff = headers_for(make_user(db, role=UserRole.MANAGER))
    assert client.get(f"{URL}/ids", headers=staff).status_code == 403
    assert client.put(f"{URL}/{tour.id}", headers=staff).status_code == 403
    assert db.query(Favorite).count() == 0
