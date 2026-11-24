"""Cancel orders whose seat hold ran out (ТЗ 4.4.1, 4.5.3 step 9).

Runs every ORDER_EXPIRY_INTERVAL_SEC from the FastAPI lifespan (app/main.py) and on demand with
`python -m scripts.expire_orders`. Free-seat counts already ignore expired holds, so this job only
puts the status in order; being late does not oversell anything.

FOR UPDATE SKIP LOCKED: if several server processes run the job at the same moment, each order
is taken by one of them only, and an order a client is changing right now is left for the next run.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Order
from app.models.enums import OrderStatus, PaymentStatus
from app.services import order_status
from app.services.payments.sessions import close_open_sessions
from app.services.seats import HOLDING_STATUSES

HOLD_EXPIRED_COMMENT = "Час на оплату минув"


def expire_orders(db: Session, now: datetime | None = None) -> int:
    """Move every checkout / awaiting_payment order with an expired hold to cancelled
    (changed_by = NULL, the System). Returns how many orders were cancelled."""
    now = now or datetime.now(timezone.utc)
    orders = db.scalars(select(Order)
                        .where(Order.status.in_(HOLDING_STATUSES), Order.hold_expires_at <= now,
                               # money has arrived: the finance controller decides, not the timer
                               Order.payment_status != PaymentStatus.PARTIALLY_PAID)
                        .order_by(Order.id)
                        .with_for_update(skip_locked=True)).all()
    for order in orders:
        close_open_sessions(db, order)   # Stripe sessions live >= 30 min, our hold is shorter
        order_status.change_status(db, order, OrderStatus.CANCELLED, None, HOLD_EXPIRED_COMMENT)
    return len(orders)


def run_expiry_job() -> int:
    """One run in its own session and transaction (used by the background loop and the CLI)."""
    with SessionLocal() as db:
        count = expire_orders(db)
        db.commit()
        return count
