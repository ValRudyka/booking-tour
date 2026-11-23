"""The demo seed fills a working catalog and can be run twice."""
from sqlalchemy import func, select

from app.models import Hotel, Tour
from app.models.enums import TourStatus
from scripts.seed_demo import HOTELS, TOURS, seed


def test_seed_demo_is_idempotent(client, db, manager):
    assert seed(db, manager) == (len(HOTELS), len(TOURS))
    assert seed(db, manager) == (0, 0)
    assert db.scalar(select(func.count()).select_from(Hotel)) == len(HOTELS)
    tours = db.scalars(select(Tour)).all()
    assert len(tours) == len(TOURS)
    assert {t.status for t in tours} == {TourStatus.ACTIVE}
    assert client.get("/api/tours").json()["total"] == len(TOURS)
