"""Public catalog and tour page — available to guests without login (ТЗ 4.4, step 2)."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DbSession
from app.models.enums import TransportType
from app.schemas.common import Page
from app.schemas.tours import TourCardOut, TourDetailOut
from app.services import catalog as catalog_service
from app.services.catalog import CatalogFilters, SortKey
from app.services.errors import DomainError

router = APIRouter(prefix="/tours", tags=["catalog"])


@router.get("", response_model=Page[TourCardOut], summary="Каталог турів (пошук, фільтри, сортування)")
def search_tours(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100, description="Пошук у назві туру та готелю")] = None,
    country_id: int | None = None,
    resort_id: int | None = None,
    departure_city_id: int | None = None,
    transport_type: TransportType | None = None,
    date_from: Annotated[date | None, Query(description="Заїзд не раніше")] = None,
    date_to: Annotated[date | None, Query(description="Заїзд не пізніше")] = None,
    nights_min: Annotated[int | None, Query(ge=1, le=30)] = None,
    nights_max: Annotated[int | None, Query(ge=1, le=30)] = None,
    price_min: Annotated[Decimal | None, Query(ge=0, description="Ціна «від», грн")] = None,
    price_max: Annotated[Decimal | None, Query(ge=0, description="Ціна «до», грн")] = None,
    stars: Annotated[list[int] | None, Query(description="Зірковість, можна кілька: stars=4&stars=5")] = None,
    featured: Annotated[bool | None, Query(description="Лише «Гарячі пропозиції»")] = None,
    has_seats: Annotated[bool | None, Query(description="Лише тури з вільними місцями")] = None,
    sort: SortKey = "date_asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
):
    filters = CatalogFilters(q=q, country_id=country_id, resort_id=resort_id,
                             departure_city_id=departure_city_id, transport_type=transport_type,
                             date_from=date_from, date_to=date_to, nights_min=nights_min,
                             nights_max=nights_max, price_min=price_min, price_max=price_max,
                             stars=stars or [], featured=featured, has_seats=has_seats)
    items, total = catalog_service.search_tours(db, filters, sort, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{tour_id}", response_model=TourDetailOut, summary="Сторінка туру")
def get_tour(tour_id: int, db: DbSession):
    try:
        return catalog_service.get_public_tour(db, tour_id)
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
