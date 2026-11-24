"""Finance controller back-office: payments register and bank-transfer confirmation (form 4.6.3.1).
Role finance only."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.deps import DbSession, require_roles
from app.models import Payment, User
from app.models.enums import PaymentMethod, PaymentType, TransactionStatus, UserRole
from app.schemas.common import Page
from app.schemas.payments import FinancePaymentOut
from app.services.errors import DomainError
from app.services.payments import finance as finance_service

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
        stripe_refund_id=payment.stripe_refund_id, created_at=payment.created_at)


@router.get("", response_model=Page[FinancePaymentOut], summary="Реєстр платежів і повернень")
def list_payments(db: DbSession, _: Finance,
                  status: TransactionStatus | None = None,
                  method: PaymentMethod | None = None,
                  kind: Annotated[PaymentType | None, Query(alias="type")] = None,
                  date_from: date | None = None,
                  date_to: date | None = None,
                  order_number: Annotated[str | None, Query(max_length=30)] = None,
                  page: Annotated[int, Query(ge=1)] = 1,
                  page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = finance_service.list_payments(
        db, status=status, method=method, kind=kind, date_from=date_from, date_to=date_to,
        order_number=order_number, page=page, page_size=page_size)
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
