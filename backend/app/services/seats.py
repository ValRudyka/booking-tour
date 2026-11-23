"""Tour seat quota (ТЗ 4.4.1, form 4.6.2.1 field 12).

free seats = seats_total − seats_sold − seats in unexpired holds of checkout / awaiting_payment
orders. An expired hold stops counting at once, even before the expiry job cancels the order.
Every change of seats (hold, more tourists, payment) locks the tour row first, so two
transactions cannot both take the last seat.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, Tour
from app.models.enums import OrderStatus

HOLDING_STATUSES = (OrderStatus.CHECKOUT, OrderStatus.AWAITING_PAYMENT)


def held_seats(now: datetime | None = None, exclude_order_id: int | None = None):
    """Correlated subquery: seats in unexpired holds of the outer query's tour.
    `now=None` uses the database clock (catalog queries)."""
    query = (select(func.coalesce(func.sum(Order.adults + Order.children), 0))
             .where(Order.tour_id == Tour.id, Order.status.in_(HOLDING_STATUSES),
                    Order.hold_expires_at > (now if now is not None else func.now())))
    if exclude_order_id is not None:
        query = query.where(Order.id != exclude_order_id)
    return query.correlate(Tour).scalar_subquery()


def free_seats_expr(now: datetime | None = None, exclude_order_id: int | None = None):
    return Tour.seats_total - Tour.seats_sold - held_seats(now, exclude_order_id)


def lock_tour(db: Session, tour_id: int) -> Tour | None:
    """SELECT ... FOR UPDATE: other transactions wait here until we commit.
    populate_existing re-reads seats_sold even if the tour is already in the session."""
    return db.scalar(select(Tour).where(Tour.id == tour_id).with_for_update()
                     .execution_options(populate_existing=True))


def free_seats(db: Session, tour_id: int, now: datetime, exclude_order_id: int | None = None) -> int:
    """Free seats of one tour; `exclude_order_id` leaves out the order being changed."""
    return db.scalar(select(free_seats_expr(now, exclude_order_id)).where(Tour.id == tour_id))
