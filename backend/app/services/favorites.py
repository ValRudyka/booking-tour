"""«Обране» of a client (ТЗ 5.7: out of MVP in 2.7, added in feature/frontend-client-profile).

The table `favorites` has been in the schema since the initial migration: one row per
(user, tour), so a tour is either in the list or not. Adding is idempotent and needs a tour that
is for sale now (the catalog's rule); a favourite that later leaves the catalog stays in the list
(`for_sale=false`) until the client removes it.
"""
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Favorite, Tour, User
from app.services import catalog
from app.services.errors import DomainError

MAX_FAVORITES = 100


def favorite_ids(db: Session, user: User) -> list[int]:
    return list(db.scalars(select(Favorite.tour_id).where(Favorite.user_id == user.id)
                           .order_by(Favorite.created_at.desc(), Favorite.tour_id.desc())))


def add_favorite(db: Session, user: User, tour_id: int) -> None:
    tour = db.get(Tour, tour_id)
    if tour is None or not catalog.is_for_sale(tour):
        raise DomainError("Тур не знайдено", 404)          # like its public page
    exists = db.scalar(select(Favorite.tour_id).where(Favorite.user_id == user.id,
                                                      Favorite.tour_id == tour_id))
    if exists is not None:
        return
    count = db.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id))
    if count >= MAX_FAVORITES:
        raise DomainError(f"В обраному може бути не більше {MAX_FAVORITES} турів", 422)
    # Two clicks at once: the second insert meets the primary key and does nothing.
    db.execute(insert(Favorite).values(user_id=user.id, tour_id=tour_id)
               .on_conflict_do_nothing(index_elements=["user_id", "tour_id"]))
    db.flush()


def remove_favorite(db: Session, user: User, tour_id: int) -> None:
    """Idempotent: removing a tour that is not in the list is fine."""
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.tour_id == tour_id))
    db.flush()
