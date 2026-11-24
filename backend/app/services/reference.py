"""Read-only reference lists for filters and forms. Archived entries are hidden, and so are the
resorts, hotels and cities of an archived country (and the hotels of an archived resort)."""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import City, Country, Hotel, InsuranceType, Resort, TransferType


def countries(db: Session) -> Sequence[Country]:
    return db.scalars(select(Country).where(Country.is_archived.is_(False))
                      .order_by(Country.name_uk)).all()


def resorts(db: Session, country_id: int | None) -> Sequence[Resort]:
    query = (select(Resort).join(Country, Resort.country_id == Country.id)
             .where(Resort.is_archived.is_(False), Country.is_archived.is_(False)))
    if country_id is not None:
        query = query.where(Resort.country_id == country_id)
    return db.scalars(query.order_by(Resort.name_uk)).all()


def hotels(db: Session, resort_id: int | None, country_id: int | None) -> Sequence[Hotel]:
    query = (select(Hotel).join(Resort, Hotel.resort_id == Resort.id)
             .join(Country, Resort.country_id == Country.id)
             .where(Hotel.is_archived.is_(False), Resort.is_archived.is_(False),
                    Country.is_archived.is_(False)))
    if resort_id is not None:
        query = query.where(Hotel.resort_id == resort_id)
    if country_id is not None:
        query = query.where(Resort.country_id == country_id)
    return db.scalars(query.order_by(Hotel.name)).all()


def cities(db: Session) -> Sequence[City]:
    return db.scalars(select(City).join(Country, City.country_id == Country.id)
                      .where(City.is_archived.is_(False), Country.is_archived.is_(False))
                      .order_by(City.name_uk)).all()


def insurance_types(db: Session) -> Sequence[InsuranceType]:
    return db.scalars(select(InsuranceType).where(InsuranceType.is_archived.is_(False))
                      .order_by(InsuranceType.price_uah, InsuranceType.id)).all()


def transfer_types(db: Session) -> Sequence[TransferType]:
    return db.scalars(select(TransferType).where(TransferType.is_archived.is_(False))
                      .order_by(TransferType.price_uah, TransferType.id)).all()
