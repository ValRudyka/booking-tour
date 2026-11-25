"""What the client may do with an order right now (OrderOut.client_actions, spec 06).

Each action is decided by the same function that enforces it when the client tries it, so the
cabinet never shows a button the backend would refuse and the rules live in one place:

| action             | decided by                                                   |
|--------------------|--------------------------------------------------------------|
| pay                | payments.service.is_payable + a hold that has not run out    |
| continue_checkout  | orders.is_editable + a hold that has not run out             |
| cancel             | orders.cancel_refusal + a hold that has not run out          |
| cancel_request     | cancellation.request_refusal                                 |
| review             | reviews.review_refusal                                       |
| view_review        | the order has a review                                       |
| download_documents | order_documents.documents_visible                            |

An order whose hold ran out gets no action: the System cancels it on the next touch (the action
endpoints do that and answer 409), so a button would only lead to an error.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Order
from app.models.enums import ClientAction as A
from app.services import cancellation, order_documents, reviews
from app.services import orders as order_service
from app.services.payments.service import is_payable


def client_actions(db: Session, order: Order, now: datetime | None = None) -> list[A]:
    actions: list[A] = []
    if not order_service.hold_ran_out(order, now):
        if is_payable(order):
            actions.append(A.PAY)
        if order_service.is_editable(order):
            actions.append(A.CONTINUE_CHECKOUT)
        if order_service.cancel_refusal(order) is None:
            actions.append(A.CANCEL)
    if cancellation.request_refusal(order) is None:
        actions.append(A.CANCEL_REQUEST)
    if reviews.trip_took_place(db, order):     # the cheap status check runs first
        if reviews.review_refusal(db, order) is None:
            actions.append(A.REVIEW)
        else:
            actions.append(A.VIEW_REVIEW)
    if order_documents.documents_visible(order):
        actions.append(A.DOWNLOAD_DOCUMENTS)
    return actions
