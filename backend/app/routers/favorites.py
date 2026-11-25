"""«Обране» of the client (spec 08 §5). Role client only; every row is the client's own."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.tours import FavoriteOut
from app.services import catalog
from app.services import favorites as favorite_service
from app.services.errors import DomainError

router = APIRouter(prefix="/me/favorites", tags=["me: favorites"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


@router.get("", response_model=Page[FavoriteOut], summary="Моє обране (нові першими)")
def list_favorites(db: DbSession, client: Client, page: Annotated[int, Query(ge=1)] = 1,
                   page_size: Annotated[int, Query(ge=1, le=50)] = 12):
    items, total = catalog.favorite_cards(db, client.id, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/ids", response_model=list[int], summary="Id турів в обраному (для кнопок «В обране»)")
def favorite_ids(db: DbSession, client: Client):
    return favorite_service.favorite_ids(db, client)


@router.put("/{tour_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Додати тур в обране")
def add_favorite(tour_id: int, db: DbSession, client: Client):
    try:
        favorite_service.add_favorite(db, client, tour_id)
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    db.commit()


@router.delete("/{tour_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Прибрати тур з обраного")
def remove_favorite(tour_id: int, db: DbSession, client: Client):
    favorite_service.remove_favorite(db, client, tour_id)
    db.commit()
