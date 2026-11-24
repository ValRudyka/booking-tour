"""In-app notifications (table `notifications`), shown in the personal account / back-office.

The client is notified from change_status() itself (status_changed below), so no status change
can forget it: paid, confirmed, documents ready, rejected, completed, cancelled by the System or
staff. A client's own action (e.g. cancelling an unpaid order) gives no notification. The refund
service adds «кошти повернено» (not a status change). Staff get notifications about cancellation
requests and refunds (ТЗ 4.5.5 step 5). E-mail copies come with feature/notifications-email.
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Notification, Order, User
from app.models.enums import OrderStatus as S
from app.models.enums import UserRole
from app.services.errors import DomainError

MANAGER_MESSAGE = "Повідомлення менеджера: "


def notify(db: Session, user_id: int, title: str, body: str, order: Order | None = None) -> Notification:
    note = Notification(user_id=user_id, order_id=order.id if order else None,
                        title=title[:200], body=body)
    db.add(note)
    db.flush()
    return note


def _client_text(order: Order, old: S, new: S) -> tuple[str, str] | None:
    n = order.number
    if new == S.PAID:
        return (f"Замовлення {n} оплачено",
                "Оплату отримано. Менеджер опрацює заявку найближчим часом.")
    if new == S.CONFIRMED:
        return (f"Бронювання {n} підтверджено",
                f"Місця підтверджено, номер бронювання (PNR): {order.pnr}. "
                f"Документи на подорож з'являться в Особистому кабінеті.")
    if new == S.DOCUMENTS_READY:
        return (f"Документи до замовлення {n} готові",
                "Ваучер та інші документи можна завантажити в Особистому кабінеті.")
    if new == S.REJECTED:
        return (f"Замовлення {n} відхилено",
                f"Причина: {order.reject_reason}. Кошти буде повернено в повному обсязі.")
    if new == S.COMPLETED:
        return (f"Подорож за замовленням {n} завершено",
                "Дякуємо, що обрали нас! Поділіться враженнями — залиште відгук про тур "
                "у розділі «Мої замовлення»: оцініть готель і наш сервіс.")
    if new == S.CANCELLED and old != S.CANCEL_REQUESTED:
        # After a cancellation request the refund service sends one «скасовано, кошти повернено».
        return f"Замовлення {n} скасовано", "Бронювання скасовано, утримані місця звільнено."
    return None


def status_changed(db: Session, order: Order, old: S, new: S, actor: User | None,
                   comment: str | None, client_message: str | None) -> None:
    """Called by change_status() after every transition."""
    if actor is not None and actor.id == order.client_id:
        return                                  # the client did it and knows already
    text = _client_text(order, old, new)
    if text is None:
        return
    title, body = text
    if new == S.CANCELLED and comment:
        body = f"{comment}. {body}"
    if client_message:
        body = f"{body}\n\n{MANAGER_MESSAGE}{client_message}"
    notify(db, order.client_id, title, body, order)


def _active(db: Session, role: UserRole) -> list[User]:
    return list(db.scalars(select(User).where(User.role == role, User.is_active.is_(True))
                           .order_by(User.id)))


def notify_finance(db: Session, order: Order, title: str, body: str) -> None:
    for user in _active(db, UserRole.FINANCE):
        notify(db, user.id, title, body, order)


def notify_managers(db: Session, order: Order, title: str, body: str) -> None:
    """The order's manager, or every manager while nobody has taken it."""
    if order.manager_id is not None:
        notify(db, order.manager_id, title, body, order)
        return
    for user in _active(db, UserRole.MANAGER):
        notify(db, user.id, title, body, order)


# ---------- the personal list
def list_own(db: Session, user: User, unread_only: bool, page: int,
             page_size: int) -> tuple[list[Notification], int, int]:
    """(page of notifications, total matching, unread count)."""
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    unread = db.scalar(select(func.count()).where(Notification.user_id == user.id,
                                                  Notification.is_read.is_(False)))
    items = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total, unread


def mark_read(db: Session, user: User, notification_id: int) -> Notification:
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user.id:     # someone else's: do not reveal it exists
        raise DomainError("Сповіщення не знайдено", 404)
    note.is_read = True
    db.flush()
    return note


def mark_all_read(db: Session, user: User) -> int:
    result = db.execute(update(Notification)
                        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
                        .values(is_read=True))
    db.flush()
    return result.rowcount
