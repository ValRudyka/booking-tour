"""Finance controller back-office: payments register, bank-transfer confirmation and refunds
(scenario 4.5.6, form 4.6.3.1). Role finance only."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.deps import DbSession, require_roles
from app.models import Order, Payment, User
from app.models.enums import PaymentMethod, PaymentOrigin, PaymentType, TransactionStatus, UserRole
from app.schemas.common import Page
from app.routers.order_views import staff_detail
from app.schemas.manager_orders import ManagerOrderDetailOut
from app.schemas.payments import FinancePaymentOut, RefundOut, RefundQueueItem, RefundRowOut
from app.services import order_documents
from app.services.errors import DomainError
from app.services.payments import finance as finance_service
from app.services.payments import refunds as refund_service
from app.services.payments import service as payment_service
from app.services.payments.gateway import PaymentGateway, get_gateway

router = APIRouter(prefix="/finance/payments", tags=["finance"])

Finance = Annotated[User, Depends(require_roles(UserRole.FINANCE))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _out(payment: Payment) -> FinancePaymentOut:
    order = payment.order
    return FinancePaymentOut(
        id=payment.id, order_id=order.id, order_number=order.number, order_status=order.status,
        order_payment_status=order.payment_status, type=payment.type, method=payment.method,
        status=payment.status, amount_uah=payment.amount_uah, paid_amount=payment.paid_amount,
        currency=payment.currency, purpose=payment.purpose, received_at=payment.received_at,
        has_statement=payment.bank_statement_path is not None,
        controller_comment=payment.controller_comment, confirmed_by=payment.confirmed_by,
        stripe_session_id=payment.stripe_session_id,
        stripe_payment_intent=payment.stripe_payment_intent,
        stripe_refund_id=payment.stripe_refund_id, origin=payment.origin,
        created_at=payment.created_at)


@router.get("", response_model=Page[FinancePaymentOut], summary="Реєстр платежів і повернень")
def list_payments(db: DbSession, _: Finance,
                  status: TransactionStatus | None = None,
                  method: PaymentMethod | None = None,
                  kind: Annotated[PaymentType | None, Query(alias="type")] = None,
                  date_from: date | None = None,
                  date_to: date | None = None,
                  order_number: Annotated[str | None, Query(max_length=30)] = None,
                  origin: Annotated[PaymentOrigin | None, Query(
                      description="app — лише справжні (тестові Stripe / перекази); demo_seed — демо-дані")] = None,
                  page: Annotated[int, Query(ge=1)] = 1,
                  page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = finance_service.list_payments(
        db, status=status, method=method, kind=kind, date_from=date_from, date_to=date_to,
        order_number=order_number, page=page, page_size=page_size, origin=origin)
    return Page(items=[_out(p) for p in items], total=total, page=page, page_size=page_size)


@router.post("/{payment_id}/confirm", response_model=FinancePaymentOut,
             summary="Підтвердити банківський переказ (повністю або частково)")
def confirm_transfer(payment_id: int, db: DbSession, controller: Finance,
                     paid_amount: Annotated[Decimal, Form(description="Фактично сплачено, грн")],
                     received_at: Annotated[datetime, Form(description="Дата надходження")],
                     purpose: Annotated[str, Form(description="Призначення платежу з виписки")],
                     comment: Annotated[str | None, Form()] = None,
                     statement: Annotated[UploadFile | None, File(description="PDF/JPG/PNG")] = None):
    try:
        payment = finance_service.confirm_transfer(
            db, controller, payment_id, paid_amount=paid_amount, received_at=received_at,
            purpose=purpose, comment=comment,
            statement=(statement.file, statement.filename) if statement else None)
    except DomainError as error:
        _raise(error)
    db.commit()
    return _out(payment)


@router.get("/{payment_id}/statement", summary="Завантажити банківську виписку")
def download_statement(payment_id: int, db: DbSession, _: Finance):
    try:
        path, name, media_type = finance_service.statement_file(db, payment_id)
    except DomainError as error:
        _raise(error)
    return FileResponse(path, media_type=media_type, filename=name)


# ---------- refunds (scenario 4.5.6, form 4.6.3.1 field 9)
orders_router = APIRouter(prefix="/finance", tags=["finance"])


@orders_router.get("/refunds", response_model=Page[RefundQueueItem],
                   summary="Черга повернень: клопотання, відхилені, невдалі повернення")
def refund_queue(db: DbSession, _: Finance,
                 page: Annotated[int, Query(ge=1)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = refund_service.refund_queue(db, page, page_size)
    rows = []
    for order in items:
        rows.append(RefundQueueItem(
            order_id=order.id, order_number=order.number, order_status=order.status,
            payment_status=order.payment_status, kind=refund_service.queue_kind(db, order),
            client_name=f"{order.client.last_name} {order.client.first_name}",
            total_uah=order.total_uah, fpv_uah=order.fpv_uah,
            cancel_reason_code=order.cancel_reason_code, cancel_reason=order.cancel_reason,
            reject_reason=order.reject_reason, created_at=order.created_at,
            **refund_service.money_summary(db, order)))
    return Page(items=rows, total=total, page=page, page_size=page_size)


def _order(db, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено")
    return order


@orders_router.get("/orders/{order_id}", response_model=ManagerOrderDetailOut,
                   summary="Замовлення для повернення: платежі, причина, довідки клієнта")
def get_order(order_id: int, db: DbSession, _: Finance):
    # The internal comment is for managers only (form 4.6.2.2, field 6).
    return staff_detail(_order(db, order_id)).model_copy(update={"internal_comment": None})


@orders_router.get("/orders/{order_id}/documents/{doc_id}/download",
                   summary="Завантажити довідку клієнта / документ замовлення")
def download_document(order_id: int, doc_id: int, db: DbSession, _: Finance):
    order = _order(db, order_id)
    try:
        path, name, media_type = order_documents.file_response_args(
            order, order_documents.get_document(order, doc_id))
    except DomainError as error:
        _raise(error)
    return FileResponse(path, media_type=media_type, filename=name)


@orders_router.post("/orders/{order_id}/refund", response_model=RefundOut,
                    summary="Оформити повернення (картка — Stripe Refund, переказ — вручну)")
def refund(order_id: int, db: DbSession, controller: Finance,
           gateway: Annotated[PaymentGateway, Depends(get_gateway)],
           fpv_amount: Annotated[Decimal, Form(description="ФПВ, грн (0 — повне повернення)")],
           comment: Annotated[str | None, Form(description="Обов'язково, якщо ФПВ > 0")] = None,
           transfer_sent_at: Annotated[datetime | None, Form(description="Дата переказу")] = None,
           transfer_details: Annotated[str | None, Form(description="Реквізити / призначення")] = None,
           manual: Annotated[bool, Form(description="Повернути картковий платіж переказом "
                                                     "(Stripe не зміг)")] = False,
           statement: Annotated[UploadFile | None, File(description="Квитанція: PDF/JPG/PNG")] = None):
    transfer = None
    if transfer_sent_at is not None or transfer_details or statement is not None:
        transfer = refund_service.TransferDetails(
            sent_at=transfer_sent_at or payment_service.utcnow(), details=transfer_details or "",
            statement=(statement.file, statement.filename) if statement else None)
    try:
        result = refund_service.refund_order(db, controller, order_id, fpv=fpv_amount,
                                             comment=comment, transfer=transfer, manual=manual,
                                             gateway=gateway)
    except DomainError as error:
        _raise(error)
    db.commit()
    order = result.order
    now = sum((r.amount_uah for r in result.rows), Decimal("0.00"))
    if result.finished:
        message = f"Повернення оформлено: {now} грн"
    else:
        message = (f"Повернення {now} грн створено, Stripe ще його обробляє — замовлення "
                   f"оновиться автоматично після підтвердження")
    return RefundOut(order_id=order.id, order_number=order.number, order_status=order.status,
                     payment_status=order.payment_status, fpv_uah=order.fpv_uah,
                     refunded_now_uah=now, rows=[RefundRowOut.model_validate(r) for r in result.rows],
                     finished=result.finished, message=message)
