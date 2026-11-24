"""Back-office «Вхідні заявки»: technical analysis of orders by the manager (ТЗ 4.5.4, 4.5.9,
form 4.6.2.2). Role manager; any manager may view, only the responsible one may change."""
from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import DbSession, require_roles
from app.models import Order, User
from app.models.enums import OrderDocumentType, OrderStatus, UserRole
from app.schemas.common import Page
from app.schemas.manager_orders import (AssignIn, ClientMessage, ConfirmIn, ManagerOrderDetailOut,
                                        ManagerOrderOut, ManagerOrderPatch, PersonOut, RejectIn,
                                        StaffDocumentOut)
from app.services import order_documents, order_processing as service, private_files
from app.services.errors import DomainError

router = APIRouter(prefix="/manager/orders", tags=["manager: orders"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(db, error: DomainError) -> NoReturn:
    # Nothing is committed: the request's session is closed and its changes are dropped.
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _row(order: Order) -> dict:
    client = order.client
    return dict(id=order.id, number=order.number, status=order.status,
                payment_status=order.payment_status, tour_id=order.tour_id,
                tour_title_uk=order.tour.title_uk, hotel_name=order.tour.hotel.name,
                start_date=order.start_date, end_date=order.end_date, adults=order.adults,
                children=order.children, total_uah=order.total_uah,
                client_name=f"{client.last_name} {client.first_name}", manager_id=order.manager_id,
                manager_name=service.short_name(order.manager), pnr=order.pnr,
                created_at=order.created_at)


def detail(order: Order) -> ManagerOrderDetailOut:
    client = order.client
    return ManagerOrderDetailOut(
        **_row(order),
        client=PersonOut(id=client.id, last_name=client.last_name, first_name=client.first_name,
                         phone=client.phone, email=client.email),
        wishes=order.wishes, insurance_type_id=order.insurance_type_id,
        transfer_type_id=order.transfer_type_id,
        promo_code=order.promo.code if order.promo else None, discount_uah=order.discount_uah,
        operator_deadline=order.operator_deadline, internal_comment=order.internal_comment,
        reject_reason=order.reject_reason, cancel_reason_code=order.cancel_reason_code,
        cancel_reason=order.cancel_reason, fpv_uah=order.fpv_uah, tourists=order.tourists,
        payments=order.payments, documents=sorted(order.documents, key=lambda d: d.id),
        history=order.history)


@router.get("", response_model=Page[ManagerOrderOut], summary="Вхідні заявки (без архівних)")
def list_orders(db: DbSession, manager: Manager,
                status_: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
                tour_id: int | None = None,
                start_from: date | None = None,
                start_to: date | None = None,
                number: Annotated[str | None, Query(max_length=30)] = None,
                mine: Annotated[bool, Query(description="Лише мої (я відповідальний)")] = False,
                overdue: Annotated[bool, Query(description="Дата туру настала, документів немає")] = False,
                page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = service.list_orders(db, manager, statuses=status_, tour_id=tour_id,
                                       start_from=start_from, start_to=start_to, number=number,
                                       mine=mine, overdue=overdue, page=page, page_size=page_size)
    return Page(items=[ManagerOrderOut(**_row(o)) for o in items], total=total, page=page,
                page_size=page_size)


@router.get("/{order_id}", response_model=ManagerOrderDetailOut, summary="Заявка (форма 4.6.2.2)")
def get_order(order_id: int, db: DbSession, _: Manager):
    try:
        return detail(service.get_order(db, order_id))
    except DomainError as error:
        _raise(db, error)


def _act(db, action) -> ManagerOrderDetailOut:
    try:
        order = action()
    except DomainError as error:
        _raise(db, error)
    db.commit()
    return detail(order)


@router.post("/{order_id}/take", response_model=ManagerOrderDetailOut, summary="Взяти в роботу")
def take(order_id: int, db: DbSession, manager: Manager):
    return _act(db, lambda: service.take(db, manager, order_id))


@router.post("/{order_id}/assign", response_model=ManagerOrderDetailOut,
             summary="Передати іншому менеджеру (поле 8 «Відповідальний»)")
def assign(order_id: int, data: AssignIn, db: DbSession, manager: Manager):
    return _act(db, lambda: service.assign(db, manager, order_id, data.manager_id))


@router.post("/{order_id}/confirm", response_model=ManagerOrderDetailOut,
             summary="Підтвердити: PNR і дедлайн оплати туроператору")
def confirm(order_id: int, data: ConfirmIn, db: DbSession, manager: Manager):
    return _act(db, lambda: service.confirm(db, manager, order_id, pnr=data.pnr,
                                            operator_deadline=data.operator_deadline,
                                            client_message=data.client_message))


@router.post("/{order_id}/reject", response_model=ManagerOrderDetailOut,
             summary="Відхилити (місця повертаються, повне повернення коштів)")
def reject(order_id: int, data: RejectIn, db: DbSession, manager: Manager):
    return _act(db, lambda: service.reject(db, manager, order_id, reason=data.reject_reason,
                                           client_message=data.client_message))


@router.post("/{order_id}/documents-ready", response_model=ManagerOrderDetailOut,
             summary="Документи готові (потрібен ваучер)")
def documents_ready(order_id: int, db: DbSession, manager: Manager, data: ClientMessage | None = None):
    message = data.client_message if data else None
    return _act(db, lambda: service.documents_ready(db, manager, order_id, message))


@router.patch("/{order_id}", response_model=ManagerOrderDetailOut, summary="Внутрішній коментар")
def update_order(order_id: int, data: ManagerOrderPatch, db: DbSession, manager: Manager):
    return _act(db, lambda: service.update_comment(db, manager, order_id, data.internal_comment))


@router.post("/{order_id}/archive", response_model=ManagerOrderDetailOut, summary="Архівувати (4.5.9)")
def archive(order_id: int, db: DbSession, manager: Manager):
    return _act(db, lambda: service.archive(db, manager, order_id))


# ---------- documents (private files)
@router.post("/{order_id}/documents", response_model=list[StaffDocumentOut],
             status_code=status.HTTP_201_CREATED, summary="Завантажити документи (PDF/JPG/PNG)")
def upload_documents(order_id: int, db: DbSession, manager: Manager,
                     doc_type: Annotated[OrderDocumentType, Form()],
                     files: Annotated[list[UploadFile], File(description="PDF, JPG або PNG")]):
    try:
        order = service.editable_order(db, manager, order_id)
        docs = order_documents.upload(db, manager, order, doc_type,
                                      [(f.file, f.filename) for f in files])
    except DomainError as error:
        _raise(db, error)
    db.commit()
    return docs


@router.delete("/{order_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Видалити документ")
def delete_document(order_id: int, doc_id: int, db: DbSession, manager: Manager):
    try:
        order = service.editable_order(db, manager, order_id)
        path = order_documents.delete(db, order, doc_id)
    except DomainError as error:
        _raise(db, error)
    db.commit()
    private_files.remove(path)                # only after the row is really gone


@router.get("/{order_id}/documents/{doc_id}/download", summary="Завантажити файл документа")
def download_document(order_id: int, doc_id: int, db: DbSession, _: Manager):
    try:
        order = service.get_order(db, order_id)
        path, name, media_type = order_documents.file_response_args(
            order, order_documents.get_document(order, doc_id))
    except DomainError as error:
        _raise(db, error)
    return FileResponse(path, media_type=media_type, filename=name)
