"""«Завершено» after the trip (ТЗ 4.4 step 10, table 4.1): the System moves «Документи готові»
orders to «Завершено» once the day after end_date has come (company's local date, clock.today()).

Runs every ORDER_COMPLETION_INTERVAL_SEC from the FastAPI lifespan (app/main.py) and on demand with
`python -m scripts.complete_orders`; FOR UPDATE SKIP LOCKED as in the expiry job.

Orders whose trip has ended but that never reached «Документи готові» are NOT completed: without
documents the system cannot tell that the service was provided. They are logged as a warning and
listed to managers with ?overdue=true:
  - «Підтверджено»: most likely the documents were handed over outside the system — the manager
    uploads them and marks «Документи готові», the next run completes the order;
  - «Оплачено» / «В роботі»: never processed — the manager rejects it (full refund);
  - «Очікує скасування» stays in the finance queue until the refund is made.
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Order
from app.models.enums import OrderStatus
from app.services import clock
from app.services.order_processing import OVERDUE_STATUSES
from app.services.order_status import change_status

logger = logging.getLogger("tour.orders")
COMPLETED_COMMENT = "Подорож завершено"


def complete_orders(db: Session, today: date | None = None) -> int:
    """documents_ready -> completed for trips that ended before `today` (changed_by = NULL)."""
    today = today or clock.today()
    orders = db.scalars(select(Order)
                        .where(Order.status == OrderStatus.DOCUMENTS_READY, Order.end_date < today)
                        .order_by(Order.id)
                        .with_for_update(skip_locked=True)).all()
    for order in orders:
        change_status(db, order, OrderStatus.COMPLETED, None, COMPLETED_COMMENT)
    stuck = db.scalars(select(Order.number).where(Order.status.in_(OVERDUE_STATUSES),
                                                  Order.end_date < today).order_by(Order.id)).all()
    if stuck:
        logger.warning("Trip ended but the order never reached documents_ready (not completed): %s",
                       ", ".join(stuck))
    return len(orders)


def run_completion_job() -> int:
    """One run in its own session and transaction (used by the background loop and the CLI)."""
    with SessionLocal() as db:
        count = complete_orders(db)
        db.commit()
        return count
