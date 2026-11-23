"""Client checkout and «Мої замовлення» (ТЗ 4.5.3, form 4.6.1.2). Role client, own orders only."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_roles
from app.models import Order, User
from app.models.enums import OrderStatus, UserRole
from app.schemas.common import Page
from app.schemas.orders import (OrderConfirm, OrderCreate, OrderDetailOut, OrderOut,
                                OrderUpdate, OrderWithPriceOut, PriceOut, QuoteRequest)
from app.services import orders as order_service
from app.services.errors import DomainError
from app.services.orders import HoldExpired
from app.services.pricing import PriceBreakdown

router = APIRouter(prefix="/orders", tags=["orders (client)"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


def _fail(db, error: DomainError) -> NoReturn:
    if isinstance(error, HoldExpired):
        db.commit()   # keep the System's cancellation, then tell the client
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _summary(order: Order) -> dict:
    return dict(
        id=order.id, number=order.number, status=order.status, payment_status=order.payment_status,
        tour_id=order.tour_id, tour_title_uk=order.tour.title_uk, hotel_name=order.tour.hotel.name,
        start_date=order.start_date, end_date=order.end_date, adults=order.adults,
        children=order.children, insurance_type_id=order.insurance_type_id,
        transfer_type_id=order.transfer_type_id,
        promo_code=order.promo.code if order.promo else None, wishes=order.wishes,
        total_uah=order.total_uah, discount_uah=order.discount_uah, rate_used=order.rate_used,
        hold_expires_at=order.hold_expires_at, offer_accepted_at=order.offer_accepted_at,
        created_at=order.created_at,
    )


def _detail(order: Order) -> dict:
    return _summary(order) | dict(tourists=order.tourists, history=order.history)


def _with_price(order: Order, price: PriceBreakdown) -> OrderWithPriceOut:
    return OrderWithPriceOut(**_detail(order), price=PriceOut.model_validate(price))


@router.post("/quote", response_model=PriceOut, summary="Розрахунок вартості (нічого не зберігає)")
def quote(data: QuoteRequest, db: DbSession, _: Client):
    try:
        return order_service.quote(db, data.model_dump())
    except DomainError as error:
        _fail(db, error)


@router.post("", response_model=OrderWithPriceOut, status_code=status.HTTP_201_CREATED,
             summary="Забронювати (статус «Оформлення», місця утримуються)")
def create_order(data: OrderCreate, db: DbSession, client: Client):
    try:
        order, price = order_service.create_order(db, client, data.model_dump())
    except DomainError as error:
        _fail(db, error)
    db.commit()
    return _with_price(order, price)


@router.get("", response_model=Page[OrderOut], summary="Мої замовлення")
def list_orders(db: DbSession, client: Client,
                status_: Annotated[OrderStatus | None, Query(alias="status")] = None,
                page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=50)] = 20):
    items, total = order_service.list_own_orders(db, client, status_, page, page_size)
    return Page(items=[OrderOut(**_summary(o)) for o in items], total=total, page=page,
                page_size=page_size)


def _own(db, client: User, order_id: int) -> Order:
    try:
        return order_service.get_own_order(db, client, order_id)
    except DomainError as error:
        _fail(db, error)


@router.get("/{order_id}", response_model=OrderDetailOut, summary="Замовлення з історією статусів")
def get_order(order_id: int, db: DbSession, client: Client):
    return OrderDetailOut(**_detail(_own(db, client, order_id)))


@router.patch("/{order_id}", response_model=OrderWithPriceOut,
              summary="Змінити туристів, послуги, промокод, побажання (лише «Оформлення»)")
def update_order(order_id: int, data: OrderUpdate, db: DbSession, client: Client):
    order = _own(db, client, order_id)
    try:
        order, price = order_service.update_order(db, order, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _fail(db, error)
    db.commit()
    return _with_price(order, price)


@router.post("/{order_id}/confirm", response_model=OrderWithPriceOut,
             summary="Перейти до оплати (ціна фіксується, «Очікує оплати»)")
def confirm_order(order_id: int, data: OrderConfirm, db: DbSession, client: Client):
    order = _own(db, client, order_id)
    try:
        order, price = order_service.confirm_order(db, client, order, data.accept_offer)
    except DomainError as error:
        _fail(db, error)
    db.commit()
    return _with_price(order, price)


@router.post("/{order_id}/cancel", response_model=OrderDetailOut,
             summary="Скасувати неоплачене замовлення (місця звільняються)")
def cancel_order(order_id: int, db: DbSession, client: Client):
    order = _own(db, client, order_id)
    try:
        order_service.cancel_order(db, client, order)
    except DomainError as error:
        _fail(db, error)
    db.commit()
    return OrderDetailOut(**_detail(order))
