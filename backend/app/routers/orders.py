"""Client checkout and «Мої замовлення» (ТЗ 4.5.3, form 4.6.1.2). Role client, own orders only."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import DbSession, require_roles
from app.models import Order, User
from app.models.enums import CancelReason, OrderStatus, UserRole
from app.schemas.common import Page
from app.schemas.manager_orders import DocumentOut
from app.schemas.orders import (OrderConfirm, OrderCreate, OrderDetailOut, OrderDetailPriceOut,
                                OrderOut, OrderUpdate, OrderWithPriceOut, PriceOut, QuoteRequest)
from app.schemas.payments import BankDetailsOut, PaymentShortOut, PayOut, PayRequest
from app.services import cancellation, order_documents
from app.services import orders as order_service
from app.services.errors import DomainError
from app.services.orders import HoldExpired
from app.services.payments import service as payment_service
from app.services.payments.gateway import PaymentGateway, get_gateway
from app.services.pricing import PriceBreakdown

router = APIRouter(prefix="/orders", tags=["orders (client)"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


def _fail(db, error: DomainError) -> NoReturn:
    if isinstance(error, HoldExpired):
        db.commit()   # keep the System's cancellation, then tell the client
    if error.loc is not None:
        # A rule about one field (a tourist's passport, name, birth date): the same shape as
        # FastAPI's own 422, so the frontend puts the message under that tourist's field.
        # "checkout_rule" tells it that msg is a Ukrainian text meant for the client.
        raise HTTPException(status_code=error.status_code, detail=[
            {"loc": list(error.loc), "msg": error.message, "type": "checkout_rule"}]) from None
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
        pnr=order.pnr, reject_reason=order.reject_reason,
        cancel_reason_code=order.cancel_reason_code, cancel_reason=order.cancel_reason,
        fpv_uah=order.fpv_uah, created_at=order.created_at,
    )


def _detail(order: Order) -> dict:
    return _summary(order) | dict(tourists=order.tourists, history=order.history,
                                  payments=order.payments)


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


@router.get("/{order_id}", response_model=OrderDetailPriceOut,
            summary="Замовлення з історією статусів і розрахунком вартості")
def get_order(order_id: int, db: DbSession, client: Client):
    """Read-only: the price is calculated, never saved (services/orders.py: order_price)."""
    order = _own(db, client, order_id)
    price = order_service.order_price(db, order)
    return OrderDetailPriceOut(**_detail(order),
                               price=PriceOut.model_validate(price) if price else None)


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


@router.post("/{order_id}/cancel-request", response_model=OrderDetailOut,
             summary="Клопотання про скасування оплаченого замовлення (форма 4.6.1.3)")
def cancel_request(order_id: int, db: DbSession, client: Client,
                   reason_code: Annotated[CancelReason, Form(description="Причина скасування")],
                   accept_penalty_policy: Annotated[bool, Form(
                       description="Згода з утриманням фактично понесених витрат (ФПВ)")],
                   details: Annotated[str | None, Form(description="Детальний опис")] = None,
                   files: Annotated[list[UploadFile] | None, File(description="Довідки: PDF або JPG")] = None):
    order = _own(db, client, order_id)
    try:
        cancellation.request_cancellation(
            db, client, order, reason=reason_code, details=details,
            accept_penalty_policy=accept_penalty_policy,
            files=[(f.file, f.filename) for f in files or []])
    except DomainError as error:
        _fail(db, error)
    db.commit()
    return OrderDetailOut(**_detail(order))


@router.post("/{order_id}/pay", response_model=PayOut,
             summary="Оплатити: картка (Stripe Checkout) або банківський переказ")
def pay_order(order_id: int, data: PayRequest, db: DbSession, client: Client,
              gateway: Annotated[PaymentGateway, Depends(get_gateway)]):
    order = _own(db, client, order_id)
    try:
        result = payment_service.start_payment(db, client, order, data.method, gateway)
    except DomainError as error:
        _fail(db, error)
    db.commit()
    order = result.order
    return PayOut(order_id=order.id, order_number=order.number, order_status=order.status,
                  payment_status=order.payment_status,
                  payment=PaymentShortOut.model_validate(result.payment) if result.payment else None,
                  checkout_url=result.checkout_url,
                  bank_details=BankDetailsOut(**result.bank) if result.bank else None,
                  message=result.message)


# ---------- trip documents (ТЗ 4.5.4 step 5): from «Підтверджено» on, own orders only
@router.get("/{order_id}/documents", response_model=list[DocumentOut],
            summary="Документи на подорож (ваучер, квитки, поліс, інфолист)")
def list_documents(order_id: int, db: DbSession, client: Client):
    return order_documents.client_documents(_own(db, client, order_id))


@router.get("/{order_id}/documents/{doc_id}/download", summary="Завантажити документ")
def download_document(order_id: int, doc_id: int, db: DbSession, client: Client):
    order = _own(db, client, order_id)
    try:
        path, name, media_type = order_documents.file_response_args(
            order, order_documents.client_document(order, doc_id))
    except DomainError as error:
        _fail(db, error)
    return FileResponse(path, media_type=media_type, filename=name)
