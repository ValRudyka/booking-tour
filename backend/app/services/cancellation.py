"""Client: cancellation request for a paid order (ТЗ 4.5.5, form 4.6.1.3).

Allowed from «Оплачено», «В роботі», «Підтверджено», «Документи готові» -> «Очікує скасування».
An unpaid order is cancelled at once without a request (orders.cancel_order). The money goes back
when the finance controller makes the refund minus ФПВ (payments/refunds.py), then the order
becomes «Скасовано» and the seats return to the quota.
"""
from sqlalchemy.orm import Session

from app.models import AuditLog, Order, User
from app.models.enums import CancelReason
from app.models.enums import OrderStatus as S
from app.services import notifications, order_documents
from app.services.errors import DomainError
from app.services.order_documents import FileUpload
from app.services.order_status import STATUS_LABELS, change_status
from app.services.payments.service import lock_order, utcnow
from app.services.seats import HOLDING_STATUSES

REQUEST_STATUSES = (S.PAID, S.IN_PROGRESS, S.CONFIRMED, S.DOCUMENTS_READY)
REASON_LABELS = {
    CancelReason.ILLNESS: "Хвороба", CancelReason.CHANGE_OF_PLANS: "Зміна планів",
    CancelReason.DATA_ERROR: "Помилка в даних", CancelReason.VISA_REFUSAL: "Відмова у візі",
    CancelReason.OTHER: "Інше",
}
MAX_DETAILS = 2000


def request_cancellation(db: Session, client: User, order: Order, *, reason: CancelReason,
                         details: str | None, accept_penalty_policy: bool,
                         files: list[FileUpload]) -> Order:
    order = lock_order(db, order.id)
    if order.status in HOLDING_STATUSES:
        raise DomainError("Неоплачене замовлення скасовується одразу, без клопотання", 409)
    if order.status not in REQUEST_STATUSES:
        raise DomainError(f"Клопотання про скасування не можна подати для замовлення в статусі "
                          f"«{STATUS_LABELS[order.status]}»", 409)
    if not accept_penalty_policy:
        raise DomainError("Підтвердіть згоду з умовами утримання фактично понесених витрат (ФПВ)", 422)
    details = (details or "").strip() or None
    if details and len(details) > MAX_DETAILS:
        raise DomainError(f"Опис причини — не довше {MAX_DETAILS} символів", 422)

    evidence = order_documents.save_cancel_evidence(db, client, order, files)
    try:
        order.cancel_reason_code, order.cancel_reason = reason, details
        # Field 5: the consent is legally relevant, so its time is kept in the audit log.
        db.add(AuditLog(user_id=client.id, entity="order", entity_id=str(order.id),
                        action="cancel_requested", new_value={
                            "reason": reason.value, "penalty_policy_accepted_at": utcnow().isoformat(),
                            "evidence_files": [d.id for d in evidence]}))
        label = REASON_LABELS[reason]
        change_status(db, order, S.CANCEL_REQUESTED, client, f"{label}: {details}" if details else label)
    except BaseException:
        for doc in evidence:
            order_documents.private_files.remove(doc.file_path)
        raise
    body = (f"Клієнт просить скасувати замовлення {order.number}. Причина: {label}"
            + (f" — {details}" if details else "") + ".")
    notifications.notify_managers(db, order, f"Клопотання про скасування {order.number}", body)
    notifications.notify_finance(db, order, f"Клопотання про скасування {order.number}",
                                 body + " Потрібне повернення коштів за вирахуванням ФПВ.")
    return order
