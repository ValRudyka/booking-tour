"""Order status model (ТЗ 4.4.1, table 4.1). The ONLY place where order.status changes.

change_status() rejects transitions that are not in the table, writes order_status_history
(changed_by = NULL means the System) and keeps the tour quota right:
  - -> paid: the held seats become sold (seats_sold += tourists), re-checked under the tour lock,
    so seats_sold never exceeds seats_total even if the hold expired before the payment came;
  - paid..cancel_requested -> rejected / cancelled: sold seats go back to the quota;
  - checkout / awaiting_payment -> cancelled: nothing to do, the hold simply stops counting.
Who may make a transition (client, manager, finance, System) is checked by the caller.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Order, OrderStatusHistory, User
from app.models.enums import OrderStatus as S
from app.services import notifications
from app.services.errors import DomainError
from app.services.seats import free_seats, lock_tour

STATUS_LABELS = {
    S.CHECKOUT: "Оформлення", S.AWAITING_PAYMENT: "Очікує оплати", S.PAID: "Оплачено",
    S.IN_PROGRESS: "В роботі", S.CONFIRMED: "Підтверджено", S.DOCUMENTS_READY: "Документи готові",
    S.COMPLETED: "Завершено", S.REJECTED: "Відхилено", S.CANCEL_REQUESTED: "Очікує скасування",
    S.CANCELLED: "Скасовано", S.ARCHIVED: "Архівний",
}

TRANSITIONS: dict[S, frozenset[S]] = {
    S.CHECKOUT: frozenset({S.AWAITING_PAYMENT, S.CANCELLED}),
    S.AWAITING_PAYMENT: frozenset({S.PAID, S.CANCELLED}),
    S.PAID: frozenset({S.IN_PROGRESS, S.CANCEL_REQUESTED}),
    S.IN_PROGRESS: frozenset({S.CONFIRMED, S.REJECTED, S.CANCEL_REQUESTED}),
    S.CONFIRMED: frozenset({S.DOCUMENTS_READY, S.CANCEL_REQUESTED}),
    S.DOCUMENTS_READY: frozenset({S.COMPLETED, S.CANCEL_REQUESTED}),
    S.COMPLETED: frozenset({S.ARCHIVED}),
    S.REJECTED: frozenset({S.ARCHIVED}),
    S.CANCEL_REQUESTED: frozenset({S.CANCELLED}),
    S.CANCELLED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}

# Statuses in which the order's seats are already written off the quota (seats_sold).
SOLD_STATUSES = frozenset({S.PAID, S.IN_PROGRESS, S.CONFIRMED, S.DOCUMENTS_READY,
                           S.CANCEL_REQUESTED})


def _history(db: Session, order: Order, old: S | None, new: S, user: User | None,
             comment: str | None) -> None:
    db.add(OrderStatusHistory(order_id=order.id, old_status=old.value if old else None,
                              new_status=new.value, changed_by=user.id if user else None,
                              comment=comment))


def record_created(db: Session, order: Order, user: User | None) -> None:
    """First history row of a new order: (none) -> checkout."""
    _history(db, order, None, order.status, user, None)
    db.flush()


def change_status(db: Session, order: Order, new_status: S, user: User | None,
                  comment: str | None = None, client_message: str | None = None) -> Order:
    """`client_message`: the manager's text for the client (form 4.6.2.2, field 7), added to the
    in-app notification that every client-visible transition creates (services/notifications)."""
    old_status = order.status
    if new_status not in TRANSITIONS[old_status]:
        raise DomainError(f"Неможливо змінити статус замовлення з «{STATUS_LABELS[old_status]}» "
                          f"на «{STATUS_LABELS[new_status]}»", 409)
    seats = order.adults + order.children

    if new_status == S.PAID:
        tour = lock_tour(db, order.tour_id)
        available = free_seats(db, tour.id, datetime.now(timezone.utc), exclude_order_id=order.id)
        if available < seats:
            raise DomainError("Немає вільних місць для оплаченого замовлення", 409)
        tour.seats_sold += seats
    elif old_status in SOLD_STATUSES and new_status in (S.REJECTED, S.CANCELLED):
        tour = lock_tour(db, order.tour_id)
        tour.seats_sold -= seats

    order.status = new_status
    _history(db, order, old_status, new_status, user, comment)
    notifications.status_changed(db, order, old_status, new_status, user, comment, client_message)
    db.flush()
    return order
