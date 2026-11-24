"""Manager: promo codes (ТЗ 4.3, form 4.6.2.3). Role manager only (not the admin, ТЗ 4.3)."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_roles
from app.models import PromoCode, User
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.promo import PromoIn, PromoOut, PromoPatch
from app.services import promo_admin as service
from app.services.errors import DomainError

router = APIRouter(prefix="/manager/promo-codes", tags=["manager: promo codes"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _out(db, promo: PromoCode) -> PromoOut:
    return PromoOut(id=promo.id, code=promo.code, discount_type=promo.discount_type,
                    discount_value=promo.discount_value, min_order_uah=promo.min_order_uah,
                    valid_from=promo.valid_from, valid_to=promo.valid_to, usage_limit=promo.usage_limit,
                    is_active=promo.is_active, created_by=promo.created_by, created_at=promo.created_at,
                    **service.counts(db, promo))


@router.get("", response_model=Page[PromoOut], summary="Промокоди")
def list_codes(db: DbSession, _: Manager, is_active: bool | None = None,
               q: Annotated[str | None, Query(max_length=20)] = None,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = service.list_codes(db, is_active=is_active, q=q, page=page, page_size=page_size)
    return Page(items=[_out(db, p) for p in items], total=total, page=page, page_size=page_size)


@router.get("/{promo_id}", response_model=PromoOut, summary="Промокод")
def get_code(promo_id: int, db: DbSession, _: Manager):
    try:
        return _out(db, service.get_code(db, promo_id))
    except DomainError as error:
        _raise(error)


@router.post("", response_model=PromoOut, status_code=status.HTTP_201_CREATED, summary="Створити промокод")
def create_code(data: PromoIn, db: DbSession, manager: Manager):
    try:
        promo = service.create_code(db, manager, data.model_dump())
    except DomainError as error:
        _raise(error)
    db.commit()
    return _out(db, promo)


@router.patch("/{promo_id}", response_model=PromoOut, summary="Редагувати / деактивувати")
def update_code(promo_id: int, data: PromoPatch, db: DbSession, manager: Manager):
    try:
        promo = service.update_code(db, manager, promo_id, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return _out(db, promo)


@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Видалити (лише промокод, який ще не використовувався)")
def delete_code(promo_id: int, db: DbSession, manager: Manager):
    try:
        service.delete_code(db, manager, promo_id)
    except DomainError as error:
        _raise(error)
    db.commit()
