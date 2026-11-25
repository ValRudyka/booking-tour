"""Manager: technical analysis of paid orders and archiving (ТЗ 4.5.4, 4.5.9, form 4.6.2.2).

«Взяти в роботу» makes the manager responsible (orders.manager_id); after that only this manager
may change the order (another one gets 409), every manager may view it. The responsible manager
can hand the order over (field 8 «Відповідальний»). Every status change goes through
change_status(), which also notifies the client and returns seats on rejection.
"""
import re
from datetime import date

from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, Tour, User
from app.models.enums import ManagerOrderSort, ManagerQueue, UserRole
from app.models.enums import OrderStatus as S
from app.services import clock, notifications, order_documents
from app.services.audit import audit
from app.services.errors import DomainError
from app.services.order_status import STATUS_LABELS, change_status
from app.services.payments.refunds import refund_finished
from app.services.payments.service import lock_order

PNR_RE = re.compile(r"^[A-Z0-9]{5,20}$")
MAX_TEXT = 2000
MAX_COMMENT = 5000
# Trip date passed, but the order never reached «Документи готові»: not completed automatically,
# shown to managers with ?overdue=true (decide: upload documents, or reject with a refund).
OVERDUE_STATUSES = (S.PAID, S.IN_PROGRESS, S.CONFIRMED)

# Which status each action needs (ТЗ 4.4.1). The action functions below and the back office's
# staff_actions (services/staff_actions.py) both read these, so a button never disagrees with
# the endpoint behind it.
TAKE_STATUSES = (S.PAID,)
DECIDE_STATUSES = (S.IN_PROGRESS,)                  # confirm or reject
DOCUMENTS_READY_STATUSES = (S.CONFIRMED,)
ARCHIVE_STATUSES = (S.COMPLETED, S.REJECTED, S.CANCELLED)
# Hand-over makes sense once the order is paid (an unpaid booking has nothing to process) and
# until it is archived.
ASSIGN_STATUSES = (S.PAID, S.IN_PROGRESS, S.CONFIRMED, S.DOCUMENTS_READY, S.CANCEL_REQUESTED,
                   S.COMPLETED, S.REJECTED, S.CANCELLED)

_SORTS = {
    ManagerOrderSort.CREATED_DESC: (Order.created_at.desc(), Order.id.desc()),
    ManagerOrderSort.CREATED_ASC: (Order.created_at.asc(), Order.id.asc()),
    ManagerOrderSort.START_ASC: (Order.start_date.asc(), Order.id.asc()),
    ManagerOrderSort.START_DESC: (Order.start_date.desc(), Order.id.desc()),
}


def short_name(user: User | None) -> str | None:
    return f"{user.last_name} {user.first_name[:1]}." if user else None


def is_overdue(order: Order) -> bool:
    """The trip date has come, but the order never reached «Документи готові»."""
    return order.status in OVERDUE_STATUSES and order.start_date <= clock.today()


def _queue_filter(queue: ManagerQueue, manager: User):
    """«Нові»: paid and nobody responsible yet; «Мої»: I am responsible; «Усі»: no filter."""
    if queue == ManagerQueue.NEW:
        return (Order.status == S.PAID) & Order.manager_id.is_(None)
    if queue == ManagerQueue.MINE:
        return Order.manager_id == manager.id
    return None


def queue_counts(db: Session, manager: User) -> dict[str, int]:
    """Counts of the three tabs over the working list (archived left out), without the search
    filters, like the unread count of the bell."""
    counts = {}
    for queue in ManagerQueue:
        query = select(func.count()).select_from(Order).where(Order.status != S.ARCHIVED)
        condition = _queue_filter(queue, manager)
        if condition is not None:
            query = query.where(condition)
        counts[queue.value] = db.scalar(query)
    return counts


def list_orders(db: Session, manager: User, *, statuses: list[S] | None, tour_id: int | None,
                start_from: date | None, start_to: date | None, number: str | None, mine: bool,
                overdue: bool, page: int, page_size: int, queue: ManagerQueue = ManagerQueue.ALL,
                client: str | None = None, created_from: date | None = None,
                created_to: date | None = None,
                sort: ManagerOrderSort = ManagerOrderSort.CREATED_DESC) -> tuple[list[Order], int]:
    query = select(Order)
    if statuses:
        query = query.where(Order.status.in_(statuses))
    else:                                       # archived orders leave the working lists (4.5.9)
        query = query.where(Order.status != S.ARCHIVED)
    condition = _queue_filter(queue, manager)
    if condition is not None:
        query = query.where(condition)
    if tour_id is not None:
        query = query.where(Order.tour_id == tour_id)
    if start_from is not None:
        query = query.where(Order.start_date >= start_from)
    if start_to is not None:
        query = query.where(Order.start_date <= start_to)
    if created_from is not None:                # Kyiv days, like the other date filters
        query = query.where(Order.created_at >= clock.day_start(created_from))
    if created_to is not None:
        query = query.where(Order.created_at < clock.day_start(created_to + timedelta(days=1)))
    if number:
        query = query.where(Order.number.icontains(number.strip(), autoescape=True))
    if client and client.strip():
        text = client.strip()
        query = query.where(Order.client_id.in_(select(User.id).where(or_(
            (User.last_name + " " + User.first_name).icontains(text, autoescape=True),
            User.first_name.icontains(text, autoescape=True),
            User.phone.icontains(text, autoescape=True),
            User.email.icontains(text, autoescape=True)))))
    if mine:
        query = query.where(Order.manager_id == manager.id)
    if overdue:
        query = query.where(Order.status.in_(OVERDUE_STATUSES), Order.start_date <= clock.today())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(selectinload(Order.tour).selectinload(Tour.hotel),
                                     selectinload(Order.client), selectinload(Order.manager))
                       .order_by(*_SORTS[sort])
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def active_managers(db: Session) -> list[User]:
    """Who an order can be handed over to (form 4.6.2.2, field 8)."""
    return list(db.scalars(select(User).where(User.role == UserRole.MANAGER, User.is_active.is_(True))
                           .order_by(User.last_name, User.first_name, User.id)))


def get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise DomainError("Замовлення не знайдено", 404)
    return order


def _locked(db: Session, order_id: int) -> Order:
    order = lock_order(db, order_id)          # two managers cannot change it at the same time
    if order is None:
        raise DomainError("Замовлення не знайдено", 404)
    return order


# ---------- refusals: why an action cannot be done now (None = it can)
# Each is used by its action (-> 409) and by staff_actions (-> a disabled button with this text).
def owner_refusal(order: Order, manager: User) -> str | None:
    if order.manager_id is not None and order.manager_id != manager.id:
        return (f"Замовлення веде інший менеджер ({short_name(order.manager)}). "
                f"Змінювати його може лише відповідальний менеджер")
    return None


def documents_ready_refusal(order: Order) -> str | None:
    return None if order_documents.has_voucher(order) else "Спершу завантажте ваучер"


def archive_refusal(db: Session, order: Order) -> str | None:
    if order.status in (S.REJECTED, S.CANCELLED) and not refund_finished(db, order):
        return "Архівувати можна після завершення повернення коштів клієнту"
    return None


def _ensure_responsible(order: Order, manager: User) -> None:
    refusal = owner_refusal(order, manager)
    if refusal:
        raise DomainError(refusal, 409)


def _ensure_status(order: Order, *allowed: S, action: str) -> None:
    if order.status not in allowed:
        names = ", ".join(f"«{STATUS_LABELS[s]}»" for s in allowed)
        raise DomainError(f"{action} можна лише в статусі {names}; зараз — "
                          f"«{STATUS_LABELS[order.status]}»", 409)


def _text(value: str | None, field: str, required: bool, limit: int = MAX_TEXT) -> str | None:
    value = (value or "").strip() or None
    if required and value is None:
        raise DomainError(f"Вкажіть {field}", 422)
    if value and len(value) > limit:
        raise DomainError(f"Поле «{field}» — не довше {limit} символів", 422)
    return value


def take(db: Session, manager: User, order_id: int) -> Order:
    """«Взяти в роботу»: paid -> in_progress, the manager becomes responsible (4.5.4 step 2)."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    _ensure_status(order, *TAKE_STATUSES, action="Взяти в роботу")
    order.manager_id = manager.id
    change_status(db, order, S.IN_PROGRESS, manager, "Заявку взято в роботу")
    return order


def assign(db: Session, manager: User, order_id: int, new_manager_id: int) -> Order:
    """Hand the order over to another manager (form 4.6.2.2, field 8), logged in audit_log."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    if order.status not in ASSIGN_STATUSES:
        raise DomainError("Передати можна лише оплачене замовлення, яке ще не архівовано", 409)
    target = db.get(User, new_manager_id)
    if target is None or target.role != UserRole.MANAGER or not target.is_active:
        raise DomainError("Відповідальним можна призначити лише активного менеджера", 422)
    if target.id == order.manager_id:
        return order
    audit(db, manager, "order", order.id, "manager_assigned",
          {"manager_id": order.manager_id}, {"manager_id": target.id})
    order.manager_id = target.id
    notifications.notify(db, target.id, f"Вам передано замовлення {order.number}",
                         f"Менеджер {short_name(manager)} передав вам супровід замовлення.", order)
    db.flush()
    db.refresh(order, ["manager"])
    return order


def confirm(db: Session, manager: User, order_id: int, *, pnr: str, operator_deadline: date,
            client_message: str | None) -> Order:
    """Seats confirmed: PNR + operator's payment deadline -> «Підтверджено» (4.5.4 step 4.2)."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    _ensure_status(order, *DECIDE_STATUSES, action="Підтвердити бронювання")
    pnr = (pnr or "").strip().upper()
    if not PNR_RE.match(pnr):
        raise DomainError("PNR — від 5 до 20 латинських літер і цифр", 422)
    if operator_deadline < clock.today():
        raise DomainError("Дедлайн оплати туроператору не може бути в минулому", 422)
    if operator_deadline > order.start_date:
        raise DomainError("Дедлайн оплати туроператору має бути не пізніше дати початку туру", 422)
    order.pnr, order.operator_deadline = pnr, operator_deadline
    change_status(db, order, S.CONFIRMED, manager, f"PNR {pnr}",
                  _text(client_message, "Повідомлення клієнту", False))
    return order


def reject(db: Session, manager: User, order_id: int, *, reason: str,
           client_message: str | None) -> Order:
    """No seats / wrong data: «Відхилено», seats back to the quota (change_status), the order
    goes to the finance queue for a full refund (4.5.4 step 4.1)."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    _ensure_status(order, *DECIDE_STATUSES, action="Відхилити заявку")
    order.reject_reason = _text(reason, "причину відхилення", True)
    change_status(db, order, S.REJECTED, manager, order.reject_reason,
                  _text(client_message, "Повідомлення клієнту", False))
    notifications.notify_finance(db, order, f"Повернення за замовленням {order.number}",
                                 f"Заявку відхилено менеджером — потрібне повне повернення коштів "
                                 f"({order.total_uah} грн).")
    return order


def documents_ready(db: Session, manager: User, order_id: int, client_message: str | None) -> Order:
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    _ensure_status(order, *DOCUMENTS_READY_STATUSES, action="Позначити «Документи готові»")
    refusal = documents_ready_refusal(order)
    if refusal:
        raise DomainError(refusal, 409)
    change_status(db, order, S.DOCUMENTS_READY, manager, None,
                  _text(client_message, "Повідомлення клієнту", False))
    return order


def update_comment(db: Session, manager: User, order_id: int, internal_comment: str | None) -> Order:
    """Form 4.6.2.2, field 6 — managers only, the client never sees it."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    order.internal_comment = _text(internal_comment, "Внутрішній коментар", False, MAX_COMMENT)
    db.flush()
    return order


def editable_order(db: Session, manager: User, order_id: int) -> Order:
    """For document upload/delete: locked and owned by this manager."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    return order


def archive(db: Session, manager: User, order_id: int) -> Order:
    """4.5.9: completed, rejected or cancelled -> «Архівний». Rejected/cancelled only when no money
    is still owed to the client (refund finished, nothing pending)."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    _ensure_status(order, *ARCHIVE_STATUSES, action="Архівувати")
    refusal = archive_refusal(db, order)
    if refusal:
        raise DomainError(refusal, 409)
    change_status(db, order, S.ARCHIVED, manager, "Замовлення архівовано")
    return order
