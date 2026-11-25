"""Back-office «Вхідні заявки»: technical analysis of orders by the manager (ТЗ 4.5.4, 4.5.9,
form 4.6.2.2). Role manager; any manager may view, only the responsible one may change."""
from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import ManagerOrderSort, ManagerQueue, OrderDocumentType, OrderStatus, UserRole
from app.routers.order_views import order_row, staff_detail
from app.schemas.manager_orders import (AssignIn, ClientMessage, ConfirmIn, DocumentRulesOut,
                                        ManagerOrderDetailOut, ManagerOrderOut, ManagerOrderPage,
                                        ManagerOrderPatch, ManagerShortOut, QueueCountsOut,
                                        RejectIn, StaffDocumentOut)
from app.services import order_documents, order_processing as service, private_files
from app.services.errors import DomainError

router = APIRouter(prefix="/manager/orders", tags=["manager: orders"])
# Lists the manager pages need besides the orders themselves.
staff_router = APIRouter(prefix="/manager", tags=["manager: orders"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(db, error: DomainError) -> NoReturn:
    # Nothing is committed: the request's session is closed and its changes are dropped.
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


@router.get("", response_model=ManagerOrderPage, summary="Вхідні заявки (без архівних)")
def list_orders(db: DbSession, manager: Manager,
                queue: Annotated[ManagerQueue, Query(description="Вкладка: нові, мої, усі")] = ManagerQueue.ALL,
                status_: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
                tour_id: int | None = None,
                start_from: date | None = None,
                start_to: date | None = None,
                created_from: Annotated[date | None, Query(description="Створено з (київська дата)")] = None,
                created_to: Annotated[date | None, Query(description="Створено по (київська дата)")] = None,
                number: Annotated[str | None, Query(max_length=30)] = None,
                client: Annotated[str | None, Query(max_length=100,
                                                    description="ПІБ, телефон або e-mail клієнта")] = None,
                mine: Annotated[bool, Query(description="Лише мої (я відповідальний)")] = False,
                overdue: Annotated[bool, Query(description="Дата туру настала, документів немає")] = False,
                sort: ManagerOrderSort = ManagerOrderSort.CREATED_DESC,
                page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = service.list_orders(db, manager, statuses=status_, tour_id=tour_id,
                                       start_from=start_from, start_to=start_to, number=number,
                                       mine=mine, overdue=overdue, page=page, page_size=page_size,
                                       queue=queue, client=client, created_from=created_from,
                                       created_to=created_to, sort=sort)
    return ManagerOrderPage(items=[ManagerOrderOut(**order_row(o)) for o in items], total=total,
                            page=page, page_size=page_size,
                            queue_counts=QueueCountsOut(**service.queue_counts(db, manager)))


# Declared before /{order_id}, which would otherwise take "document-rules" for an id.
@router.get("/document-rules", response_model=DocumentRulesOut,
            summary="Правила завантаження документів (типи, кількість, розмір)")
def document_rules(_: Manager):
    return DocumentRulesOut(**order_documents.upload_rules())


@router.get("/{order_id}", response_model=ManagerOrderDetailOut, summary="Заявка (форма 4.6.2.2)")
def get_order(order_id: int, db: DbSession, manager: Manager):
    try:
        return staff_detail(db, service.get_order(db, order_id), manager)
    except DomainError as error:
        _raise(db, error)


def _act(db, manager: User, action) -> ManagerOrderDetailOut:
    try:
        order = action()
    except DomainError as error:
        _raise(db, error)
    db.commit()
    return staff_detail(db, order, manager)


@router.post("/{order_id}/take", response_model=ManagerOrderDetailOut, summary="Взяти в роботу")
def take(order_id: int, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.take(db, manager, order_id))


@router.post("/{order_id}/assign", response_model=ManagerOrderDetailOut,
             summary="Передати іншому менеджеру (поле 8 «Відповідальний»)")
def assign(order_id: int, data: AssignIn, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.assign(db, manager, order_id, data.manager_id))


@router.post("/{order_id}/confirm", response_model=ManagerOrderDetailOut,
             summary="Підтвердити: PNR і дедлайн оплати туроператору")
def confirm(order_id: int, data: ConfirmIn, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.confirm(db, manager, order_id, pnr=data.pnr,
                                            operator_deadline=data.operator_deadline,
                                            client_message=data.client_message))


@router.post("/{order_id}/reject", response_model=ManagerOrderDetailOut,
             summary="Відхилити (місця повертаються, повне повернення коштів)")
def reject(order_id: int, data: RejectIn, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.reject(db, manager, order_id, reason=data.reject_reason,
                                           client_message=data.client_message))


@router.post("/{order_id}/documents-ready", response_model=ManagerOrderDetailOut,
             summary="Документи готові (потрібен ваучер)")
def documents_ready(order_id: int, db: DbSession, manager: Manager, data: ClientMessage | None = None):
    message = data.client_message if data else None
    return _act(db, manager, lambda: service.documents_ready(db, manager, order_id, message))


@router.patch("/{order_id}", response_model=ManagerOrderDetailOut, summary="Внутрішній коментар")
def update_order(order_id: int, data: ManagerOrderPatch, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.update_comment(db, manager, order_id, data.internal_comment))


@router.post("/{order_id}/archive", response_model=ManagerOrderDetailOut, summary="Архівувати (4.5.9)")
def archive(order_id: int, db: DbSession, manager: Manager):
    return _act(db, manager, lambda: service.archive(db, manager, order_id))


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


@staff_router.get("/managers", response_model=list[ManagerShortOut],
                  summary="Активні менеджери (кому передати замовлення)")
def list_managers(db: DbSession, _: Manager):
    return [ManagerShortOut(id=u.id, name=f"{u.last_name} {u.first_name}")
            for u in service.active_managers(db)]
