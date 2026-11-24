"""Public tour catalog: search, filters, sorting, pagination (ТЗ 4.2, 4.4 step 2, 4.5.2).

Price filters and sorting work in UAH although tours are priced in EUR/USD/UAH: the price is
converted in SQL with the admin's commercial rate (currency_rates), so the database can filter,
sort and paginate in one query.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import CurrencyRate, Hotel, Resort, Tour
from app.models.enums import TourStatus, TransportType
from app.schemas.reference import CityOut, CountryOut, HotelOut, ResortOut
from app.schemas.tours import ProgramDayOut, TourCardOut, TourDetailOut, TourImageOut
from app.services import clock
from app.services.errors import DomainError
from app.services.reviews import tour_review_stats
from app.services.seats import free_seats_expr

SortKey = Literal["price_asc", "price_desc", "date_asc", "date_desc", "rating_desc"]


@dataclass
class CatalogFilters:
    q: str | None = None
    country_id: int | None = None
    resort_id: int | None = None
    departure_city_id: int | None = None
    transport_type: TransportType | None = None
    date_from: date | None = None
    date_to: date | None = None
    nights_min: int | None = None
    nights_max: int | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    stars: list[int] = field(default_factory=list)
    featured: bool | None = None
    has_seats: bool | None = None


def _query() -> tuple[Select, dict]:
    free_seats = free_seats_expr()  # same rule as the checkout (services/seats.py)
    price_uah = func.round(Tour.base_price * CurrencyRate.rate_to_uah, 2)
    query = (select(Tour, price_uah.label("price_from_uah"), free_seats.label("free_seats"),
                    CurrencyRate.rate_to_uah)
             .join(Hotel, Tour.hotel_id == Hotel.id)
             .join(Resort, Hotel.resort_id == Resort.id)
             .join(CurrencyRate, CurrencyRate.currency == Tour.currency)
             # For sale = published and at least one start date from tomorrow (Kyiv), the
             # earliest date an order accepts (services/orders.py). On its last start day a
             # tour is no longer listed, and its page is 404.
             .where(Tour.status == TourStatus.ACTIVE, Tour.departure_to >= clock.tomorrow())
             .options(selectinload(Tour.hotel).selectinload(Hotel.resort).selectinload(Resort.country),
                      selectinload(Tour.departure_city), selectinload(Tour.images)))
    return query, {"free_seats": free_seats, "price_uah": price_uah}


def _apply_filters(query: Select, f: CatalogFilters, expr: dict) -> Select:
    if f.q:
        query = query.where(or_(Tour.title_uk.icontains(f.q, autoescape=True),
                                Tour.title_en.icontains(f.q, autoescape=True),
                                Hotel.name.icontains(f.q, autoescape=True)))
    if f.country_id is not None:
        query = query.where(Resort.country_id == f.country_id)
    if f.resort_id is not None:
        query = query.where(Hotel.resort_id == f.resort_id)
    if f.departure_city_id is not None:
        query = query.where(Tour.departure_city_id == f.departure_city_id)
    if f.transport_type is not None:
        query = query.where(Tour.transport_type == f.transport_type)
    # A tour matches when its range of start dates overlaps the requested range.
    if f.date_from is not None:
        query = query.where(Tour.departure_to >= f.date_from)
    if f.date_to is not None:
        query = query.where(Tour.departure_from <= f.date_to)
    if f.nights_min is not None:
        query = query.where(Tour.nights >= f.nights_min)
    if f.nights_max is not None:
        query = query.where(Tour.nights <= f.nights_max)
    if f.price_min is not None:
        query = query.where(expr["price_uah"] >= f.price_min)
    if f.price_max is not None:
        query = query.where(expr["price_uah"] <= f.price_max)
    if f.stars:
        query = query.where(Hotel.stars.in_(f.stars))
    if f.featured is not None:
        query = query.where(Tour.is_featured == f.featured)
    if f.has_seats is True:
        query = query.where(expr["free_seats"] > 0)
    elif f.has_seats is False:
        query = query.where(expr["free_seats"] <= 0)
    return query


def _order(query: Select, sort: SortKey, expr: dict) -> Select:
    order = {
        "price_asc": expr["price_uah"].asc(),
        "price_desc": expr["price_uah"].desc(),
        "date_asc": Tour.departure_from.asc(),
        "date_desc": Tour.departure_from.desc(),
        "rating_desc": Hotel.rating_avg.desc().nulls_last(),  # from published reviews
    }[sort]
    return query.order_by(order, Tour.id)  # id keeps pages stable when values are equal


def _card_fields(tour: Tour, price_uah: Decimal, free_seats: int) -> dict:
    resort = tour.hotel.resort
    return dict(
        id=tour.id, title_uk=tour.title_uk, title_en=tour.title_en,
        country=CountryOut.model_validate(resort.country), resort=ResortOut.model_validate(resort),
        hotel=HotelOut.model_validate(tour.hotel), transport_type=tour.transport_type,
        departure_city=CityOut.model_validate(tour.departure_city) if tour.departure_city else None,
        departure_from=tour.departure_from, departure_to=tour.departure_to, nights=tour.nights,
        currency=tour.currency, base_price=tour.base_price, price_from_uah=price_uah,
        free_seats=max(free_seats, 0), is_featured=tour.is_featured,
        image_url=f"/uploads/{tour.images[0].file_path}" if tour.images else None,
    )


def search_tours(db: Session, filters: CatalogFilters, sort: SortKey, page: int,
                 page_size: int) -> tuple[list[TourCardOut], int]:
    query, expr = _query()
    query = _apply_filters(query, filters, expr)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.execute(_order(query, sort, expr).offset((page - 1) * page_size).limit(page_size)).all()
    cards = [TourCardOut(**_card_fields(tour, price, free)) for tour, price, free, _rate in rows]
    return cards, total


def get_public_tour(db: Session, tour_id: int) -> TourDetailOut:
    """Tour page: drafts, archived and finished tours are not public (404)."""
    query, _ = _query()
    row = db.execute(query.where(Tour.id == tour_id)
                     .options(selectinload(Tour.program_days))).first()
    if row is None:
        raise DomainError("Тур не знайдено", 404)
    tour, price, free, rate = row
    child_price = tour.child_price if tour.child_price is not None else tour.base_price
    reviews_count, service_rating_avg = tour_review_stats(db, tour.id)
    return TourDetailOut(
        **_card_fields(tour, price, free),
        child_price=tour.child_price,
        child_price_uah=(child_price * rate).quantize(Decimal("0.01"), ROUND_HALF_UP),  # = SQL ROUND
        flight_out=tour.flight_out, flight_back=tour.flight_back, description=tour.description,
        hotel_description=tour.hotel.description,
        program_days=[ProgramDayOut.model_validate(d) for d in tour.program_days],
        images=[TourImageOut.model_validate(i) for i in tour.images],
        reviews_count=reviews_count, service_rating_avg=service_rating_avg,
    )
