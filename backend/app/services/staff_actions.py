"""What a manager may do with an order right now (ManagerOrderDetailOut.staff_actions, spec 09).

The back-office counterpart of order_actions.client_actions. Each action is listed only in the
statuses where it makes sense (the same status tuples the action functions check); for each
listed action the same refusal function that the endpoint enforces decides whether it is
allowed, and its text is returned as the reason. The frontend shows an allowed action as a
button and a refused one as a disabled button with the reason, and never mirrors these rules.

| action           | listed in statuses (order_processing / order_documents) | refused by             |
|------------------|---------------------------------------------------------|------------------------|
| take             | TAKE_STATUSES (paid)                                    | owner_refusal          |
| confirm, reject  | DECIDE_STATUSES (in_progress)                           | owner_refusal          |
| upload_documents | order_documents.UPLOAD_STATUSES                         | owner, upload_refusal  |
| documents_ready  | DOCUMENTS_READY_STATUSES (confirmed)                    | owner, needs a voucher |
| archive          | ARCHIVE_STATUSES                                        | owner, archive_refusal |
| assign           | ASSIGN_STATUSES (paid .. cancelled, not archived)       | owner_refusal          |
| edit_comment     | every status                                            | owner_refusal          |

Every manager may view an order and download its documents, so those are not actions. Other
roles get no actions (finance's refunds come with spec 12).
"""
from sqlalchemy.orm import Session

from app.models import Order, User
from app.models.enums import StaffAction as A
from app.models.enums import UserRole
from app.services import order_documents
from app.services import order_processing as p


def staff_actions(db: Session, order: Order, viewer: User) -> list[dict]:
    if viewer.role != UserRole.MANAGER:
        return []
    owner = p.owner_refusal(order, viewer)
    actions: list[dict] = []

    def add(action: A, listed: bool, refusal=None) -> None:
        if not listed:
            return
        # Only another manager's order is refused before the precondition is looked at.
        reason = owner or (refusal() if refusal else None)
        actions.append(dict(action=action, allowed=reason is None, reason=reason))

    status = order.status
    add(A.TAKE, status in p.TAKE_STATUSES)
    add(A.CONFIRM, status in p.DECIDE_STATUSES)
    add(A.REJECT, status in p.DECIDE_STATUSES)
    add(A.UPLOAD_DOCUMENTS, status in order_documents.UPLOAD_STATUSES,
        lambda: order_documents.upload_refusal(order))
    add(A.DOCUMENTS_READY, status in p.DOCUMENTS_READY_STATUSES,
        lambda: p.documents_ready_refusal(order))
    add(A.ARCHIVE, status in p.ARCHIVE_STATUSES, lambda: p.archive_refusal(db, order))
    add(A.ASSIGN, status in p.ASSIGN_STATUSES)
    add(A.EDIT_COMMENT, True)
    return actions


def document_can_delete(order: Order, viewer: User, doc) -> bool:
    """StaffOrderDocumentOut.can_delete: the delete endpoint would accept it from this user."""
    if viewer.role != UserRole.MANAGER or p.owner_refusal(order, viewer):
        return False
    return order_documents.delete_refusal(order, doc) is None
