"""Order documents (ТЗ 4.5.4 step 4.2, form 4.6.2.2 field 5; form 4.6.1.3 field 4).

Trip documents (voucher, air ticket, insurance policy, info sheet) are uploaded by the order's
manager and downloaded by the client from «Підтверджено» on. The client's cancellation evidence
is seen by staff only. All files are private (upload_dir/private/orders/<order id>/...): never
under the public /uploads/tours mount, handed out only by endpoints that check the user's rights.
"""
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, OrderDocument, User
from app.models.enums import TRIP_DOCUMENT_TYPES, OrderDocumentType
from app.models.enums import OrderStatus as S
from app.services import private_files
from app.services.errors import DomainError

DOC_LABELS = {
    OrderDocumentType.VOUCHER: "Ваучер", OrderDocumentType.AIR_TICKET: "Авіаквиток",
    OrderDocumentType.INSURANCE_POLICY: "Страховий поліс", OrderDocumentType.INFO_SHEET: "Інфолист",
    OrderDocumentType.CANCEL_EVIDENCE: "Довідка до клопотання",
}
# The manager attaches documents once the booking is confirmed (scenario 4.5.4, step 4.2).
UPLOAD_STATUSES = (S.CONFIRMED, S.DOCUMENTS_READY)
# The client sees trip documents from «Підтверджено» on, also after the trip.
CLIENT_STATUSES = (S.CONFIRMED, S.DOCUMENTS_READY, S.COMPLETED, S.ARCHIVED)

FileUpload = tuple[BinaryIO, str | None]


def _save_all(db: Session, order: Order, user: User, doc_type: OrderDocumentType,
              files: list[FileUpload], allowed: dict[bytes, str], wrong_type: str) -> list[OrderDocument]:
    saved: list[str] = []
    try:
        for source, filename in files:
            saved.append(private_files.save_private(
                f"orders/{order.id}", source, filename, allowed=allowed,
                max_mb=settings.max_document_mb, wrong_type=wrong_type,
                too_big=f"Файл «{{name}}» більший за {settings.max_document_mb} МБ"))
        docs = [OrderDocument(order_id=order.id, doc_type=doc_type, file_path=path,
                              uploaded_by=user.id) for path in saved]
        db.add_all(docs)
        db.flush()
    except BaseException:
        for path in saved:                    # all or nothing: no orphan files
            private_files.remove(path)
        raise
    db.refresh(order, ["documents"])
    return docs


def upload(db: Session, manager: User, order: Order, doc_type: OrderDocumentType,
           files: list[FileUpload]) -> list[OrderDocument]:
    if doc_type not in TRIP_DOCUMENT_TYPES:
        raise DomainError("Менеджер завантажує лише ваучер, авіаквиток, страховий поліс або інфолист", 422)
    if order.status not in UPLOAD_STATUSES:
        raise DomainError("Документи додаються після підтвердження бронювання "
                          "(статус «Підтверджено» або «Документи готові»)", 409)
    if not files:
        raise DomainError("Додайте хоча б один файл", 422)
    existing = db.scalar(select(func.count()).where(OrderDocument.order_id == order.id))
    if existing + len(files) > settings.max_documents_per_order:
        raise DomainError(f"До замовлення можна додати не більше "
                          f"{settings.max_documents_per_order} документів", 409)
    return _save_all(db, order, manager, doc_type, files, private_files.PDF_JPG_PNG,
                     "Файл «{name}»: документ має бути PDF, JPG або PNG")


def save_cancel_evidence(db: Session, client: User, order: Order,
                         files: list[FileUpload]) -> list[OrderDocument]:
    if len(files) > settings.max_cancel_evidence_files:
        raise DomainError(f"Можна додати не більше {settings.max_cancel_evidence_files} файлів", 422)
    if not files:
        return []
    return _save_all(db, order, client, OrderDocumentType.CANCEL_EVIDENCE, files,
                     private_files.PDF_JPG, "Файл «{name}»: довідка має бути PDF або JPG")


def get_document(order: Order, doc_id: int) -> OrderDocument:
    doc = next((d for d in order.documents if d.id == doc_id), None)
    if doc is None:
        raise DomainError("Документ не знайдено", 404)
    return doc


def delete(db: Session, order: Order, doc_id: int) -> str:
    """Returns the stored path; the caller removes the file after the commit."""
    doc = get_document(order, doc_id)
    if doc.doc_type not in TRIP_DOCUMENT_TYPES:
        raise DomainError("Довідки клієнта не видаляються", 409)
    if order.status not in UPLOAD_STATUSES:
        raise DomainError("Документи цього замовлення вже не змінюються", 409)
    if (order.status == S.DOCUMENTS_READY and doc.doc_type == OrderDocumentType.VOUCHER
            and sum(d.doc_type == OrderDocumentType.VOUCHER for d in order.documents) == 1):
        raise DomainError("Не можна видалити останній ваучер: документи вже передано клієнту", 409)
    path = doc.file_path
    db.delete(doc)
    db.flush()
    db.refresh(order, ["documents"])
    return path


def has_voucher(order: Order) -> bool:
    return any(d.doc_type == OrderDocumentType.VOUCHER for d in order.documents)


def client_documents(order: Order) -> list[OrderDocument]:
    if order.status not in CLIENT_STATUSES:
        return []
    return sorted((d for d in order.documents if d.doc_type in TRIP_DOCUMENT_TYPES), key=lambda d: d.id)


def client_document(order: Order, doc_id: int) -> OrderDocument:
    """Another client's order never gets here (404 earlier); not yet visible = 404 too."""
    doc = next((d for d in client_documents(order) if d.id == doc_id), None)
    if doc is None:
        raise DomainError("Документ не знайдено", 404)
    return doc


def file_response_args(order: Order, doc: OrderDocument) -> tuple[str, str, str]:
    """(absolute path, download name, media type). The name is built by the server."""
    path = private_files.absolute(doc.file_path)
    if not path.exists():
        raise DomainError("Файл документа не знайдено", 404)
    ext, media = private_files.media_type(doc.file_path)
    return str(path), f"{doc.doc_type.value}-{order.number}-{doc.id}.{ext}", media
