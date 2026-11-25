"""Tour meal plan, «Що включено / не включено» and the alphabetical catalog sort
(form 4.6.2.1 rows added in feature/catalog-improvements)."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import MealPlan, TourStatus
from tests.factories import make_active_tour, make_hotel, make_tour
from tests.test_manager_tours import URL, create, payload

CATALOG = "/api/tours"


@pytest.fixture()
def hotel(db):
    return make_hotel(db, name="Rixos", resort_en="Antalya", stars=5)


def catalog(client, **params):
    response = client.get(CATALOG, params={"page_size": 50, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


# ---------- manager form
def test_manager_saves_meal_plan_and_cleaned_lists(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel, meal_plan="ai",
                  included=["  Авіапереліт ", "", "Проживання", "Авіапереліт", "Харчування   за програмою"],
                  excluded=["Медичне страхування — обирається під час бронювання"])
    assert tour["meal_plan"] == "ai"
    # trimmed, inner spaces collapsed, empty and repeated lines dropped, order kept
    assert tour["included"] == ["Авіапереліт", "Проживання", "Харчування за програмою"]
    assert tour["excluded"] == ["Медичне страхування — обирається під час бронювання"]

    changed = client.patch(f"{URL}/{tour['id']}", headers=manager_headers,
                           json={"meal_plan": None, "included": ["Трансфер у межах курорту"]})
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["meal_plan"], body["included"], body["excluded"]) == (
        None, ["Трансфер у межах курорту"], tour["excluded"])


def test_lists_default_to_empty(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel)
    assert (tour["meal_plan"], tour["included"], tour["excluded"]) == (None, [], [])


@pytest.mark.parametrize("field, values, message", [
    ("included", [f"Пункт {n}" for n in range(21)], "Що включено: не більше 20 пунктів"),
    ("excluded", ["x" * 201], "Що не включено: кожен пункт — не довше 200 символів"),
])
def test_list_limits(client, manager_headers, hotel, field, values, message):
    response = client.post(URL, headers=manager_headers, json=payload(hotel.id, **{field: values}))
    assert response.status_code == 422 and response.json()["detail"] == message


def test_unknown_meal_plan_is_rejected(client, manager_headers, hotel):
    response = client.post(URL, headers=manager_headers, json=payload(hotel.id, meal_plan="all"))
    assert response.status_code == 422


def test_copy_keeps_meal_plan_and_lists(client, manager_headers, hotel):
    tour = create(client, manager_headers, hotel, meal_plan="hb", included=["Сніданки й вечері"])
    copy = client.post(f"{URL}/{tour['id']}/copy", headers=manager_headers).json()
    assert (copy["meal_plan"], copy["included"]) == ("hb", ["Сніданки й вечері"])


def test_database_rejects_an_unknown_meal_plan(db, manager):
    tour = make_tour(db, manager)
    with pytest.raises(IntegrityError):
        db.execute(type(tour).__table__.update().where(type(tour).id == tour.id)
                   .values(meal_plan="all_you_can_eat"))


# ---------- public catalog and tour page
def test_meal_filter_matches_any_of_the_chosen_plans(client, db, manager):
    ai = make_active_tour(db, manager, title_uk="AI", meal_plan=MealPlan.AI)
    uai = make_active_tour(db, manager, title_uk="UAI", meal_plan=MealPlan.UAI)
    make_active_tour(db, manager, title_uk="BB", meal_plan=MealPlan.BB)
    make_active_tour(db, manager, title_uk="Не вказано")

    items = catalog(client, meal_plan=["ai", "uai"])
    assert sorted(t["id"] for t in items) == sorted([ai.id, uai.id])
    assert {t["meal_plan"] for t in items} == {"ai", "uai"}
    assert len(catalog(client)) == 4                       # no filter: tours without a plan too
    assert client.get(CATALOG, params={"meal_plan": "xx"}).status_code == 422


def test_title_sort_follows_the_ukrainian_alphabet(client, db, manager):
    titles = ["Їжак", "Єгипет", "Іспанія", "Ґалина", "Анталія", "Дубай", "Гірський", "Иркутськ"]
    for title in titles:
        make_active_tour(db, manager, title_uk=title)
    got = [t["title_uk"] for t in catalog(client, sort="title_asc")]
    assert got == ["Анталія", "Гірський", "Ґалина", "Дубай", "Єгипет", "Иркутськ", "Іспанія", "Їжак"]


def test_tour_page_shows_the_lists_and_the_card_does_not(client, db, manager):
    tour = make_active_tour(db, manager, meal_plan=MealPlan.FB, included=["Проживання"],
                            excluded=["Екскурсії"])
    page = client.get(f"{CATALOG}/{tour.id}").json()
    assert (page["meal_plan"], page["included"], page["excluded"]) == ("fb", ["Проживання"], ["Екскурсії"])
    card = catalog(client)[0]
    assert card["meal_plan"] == "fb" and "included" not in card and "excluded" not in card


def test_draft_tours_stay_out_of_the_meal_filter(client, db, manager):
    make_tour(db, manager, status=TourStatus.DRAFT, meal_plan=MealPlan.AI)
    assert catalog(client, meal_plan="ai") == []


def test_migration_stops_without_the_icu_collation(monkeypatch):
    """On a PostgreSQL without ICU the migration must fail at once, with a clear message."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    path = next((Path(__file__).parent.parent / "alembic" / "versions").glob("*_c3d8a1f5b742_*.py"))
    spec = importlib.util.spec_from_file_location("migration_c3d8a1f5b742", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    added = []
    bind = SimpleNamespace(scalar=lambda *args, **kwargs: 0)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: bind,
                                                         add_column=lambda *a, **k: added.append(a)))
    monkeypatch.setattr(migration, "context", SimpleNamespace(is_offline_mode=lambda: False))
    with pytest.raises(RuntimeError, match='collation "uk-x-icu" not found'):
        migration.upgrade()
    assert added == []          # nothing changed before the check
