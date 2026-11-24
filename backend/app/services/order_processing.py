"""Manager: technical analysis of paid orders and archiving (ТЗ 4.5.4, 4.5.9, form 4.6.2.2).

«Взяти в роботу» makes the manager responsible (orders.manager_id); after that only this manager
may change the order (another one gets 409), every manager may view it. The responsible manager
can hand the order over (field 8 «Відповідальний»). Every status change goes through
change_status(), which also notifies the client and returns seats on rejection.
"""
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditLog, Order, Tour, User
from app.models.enums import OrderStatus as S
from app.models.enums import UserRole
from app.services import clock, notifications, order_documents
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


def short_name(user: User | None) -> str | None:
    return f"{user.last_name} {user.first_name[:1]}." if user else None


def list_orders(db: Session, manager: User, *, statuses: list[S] | None, tour_id: int | None,
                start_from: date | None, start_to: date | None, number: str | None, mine: bool,
                overdue: bool, page: int, page_size: int) -> tuple[list[Order], int]:
    query = select(Order)
    if statuses:
        query = query.where(Order.status.in_(statuses))
    else:                                       # archived orders leave the working lists (4.5.9)
        query = query.where(Order.status != S.ARCHIVED)
    if tour_id is not None:
        query = query.where(Order.tour_id == tour_id)
    if start_from is not None:
        query = query.where(Order.start_date >= start_from)
    if start_to is not None:
        query = query.where(Order.start_date <= start_to)
    if number:
        query = query.where(Order.number.icontains(number.strip(), autoescape=True))
    if mine:
        query = query.where(Order.manager_id == manager.id)
    if overdue:
        query = query.where(Order.status.in_(OVERDUE_STATUSES), Order.start_date <= clock.today())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(selectinload(Order.tour).selectinload(Tour.hotel),
                                     selectinload(Order.client), selectinload(Order.manager))
                       .order_by(Order.created_at.desc(), Order.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


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


def _ensure_responsible(order: Order, manager: User) -> None:
    if order.manager_id is not None and order.manager_id != manager.id:
        raise DomainError(f"Замовлення веде інший менеджер ({short_name(order.manager)}). "
                          f"Змінювати його може лише відповідальний менеджер", 409)


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
    _ensure_status(order, S.PAID, action="Взяти в роботу")
    order.manager_id = manager.id
    change_status(db, order, S.IN_PROGRESS, manager, "Заявку взято в роботу")
    return order


def assign(db: Session, manager: User, order_id: int, new_manager_id: int) -> Order:
    """Hand the order over to another manager (form 4.6.2.2, field 8), logged in audit_log."""
    order = _locked(db, order_id)
    _ensure_responsible(order, manager)
    if order.status == S.ARCHIVED:
        raise DomainError("Архівне замовлення не передається", 409)
    target = db.get(User, new_manager_id)
    if target is None or target.role != UserRole.MANAGER or not target.is_active:
        raise DomainError("Відповідальним можна призначити лише активного менеджера", 422)
    if target.id == order.manager_id:
        return order
    db.add(AuditLog(user_id=manager.id, entity="order", entity_id=str(order.id), action="manager_assigned",
                    old_value={"manager_id": order.manager_id}, new_value={"manager_id": target.id}))
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
    _ensure_status(order, S.IN_PROGRESS, action="Підтвердити бронювання")
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
    _ensure_status(order, S.IN_PROGRESS, action="Відхилити заявку")
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
    _ensure_status(order, S.CONFIRMED, action="Позначити «Документи готові»")
    if not order_documents.has_voucher(order):
        raise DomainError("Спершу завантажте ваучер", 409)
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
    _ensure_status(order, S.COMPLETED, S.REJECTED, S.CANCELLED, action="Архівувати")
    if order.status in (S.REJECTED, S.CANCELLED) and not refund_finished(db, order):
        raise DomainError("Архівувати можна після завершення повернення коштів клієнту", 409)
    change_status(db, order, S.ARCHIVED, manager, "Замовлення архівовано")
    return order
