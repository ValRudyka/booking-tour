"""Public reference lists for filters; archived entries are hidden."""
from tests.factories import city, country, make_hotel, resort

URL = "/api/reference"


def test_countries(client, db):
    body = client.get(f"{URL}/countries").json()
    assert {"UA", "TR", "EG"} <= {c["iso_code"] for c in body}
    country(db, "CY").is_archived = True
    db.flush()
    assert "CY" not in {c["iso_code"] for c in client.get(f"{URL}/countries").json()}


def test_resorts_by_country(client, db):
    body = client.get(f"{URL}/resorts", params={"country_id": country(db, "EG").id}).json()
    assert {r["name_en"] for r in body} == {"Hurghada", "Sharm El Sheikh"}
    resort(db, "Hurghada").is_archived = True
    db.flush()
    body = client.get(f"{URL}/resorts", params={"country_id": country(db, "EG").id}).json()
    assert [r["name_en"] for r in body] == ["Sharm El Sheikh"]
    assert len(client.get(f"{URL}/resorts").json()) > 10   # without a filter: all resorts


def test_hotels_by_resort_and_country(client, db):
    rixos = make_hotel(db, name="Rixos", resort_en="Antalya", stars=5)
    make_hotel(db, name="Akra", resort_en="Kemer", stars=4)
    make_hotel(db, name="Old", resort_en="Antalya", is_archived=True)
    make_hotel(db, name="Steigenberger", resort_en="Hurghada")
    body = client.get(f"{URL}/hotels", params={"resort_id": resort(db, "Antalya").id}).json()
    assert body == [{"id": rixos.id, "resort_id": rixos.resort_id, "name": "Rixos", "stars": 5,
                     "rating_avg": None}]
    body = client.get(f"{URL}/hotels", params={"country_id": country(db, "TR").id}).json()
    assert [h["name"] for h in body] == ["Akra", "Rixos"]
    # a hotel of an archived resort is hidden too
    resort(db, "Kemer").is_archived = True
    db.flush()
    assert [h["name"] for h in client.get(f"{URL}/hotels").json()] == ["Rixos", "Steigenberger"]


def test_cities(client, db):
    body = client.get(f"{URL}/cities").json()
    assert {"Kyiv", "Warsaw"} <= {c["name_en"] for c in body}
    city(db, "Kyiv").is_archived = True
    db.flush()
    assert "Kyiv" not in {c["name_en"] for c in client.get(f"{URL}/cities").json()}
