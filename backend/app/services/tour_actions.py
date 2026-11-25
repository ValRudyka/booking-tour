"""What a manager may do with a tour right now (ManagerTourOut.tour_actions, spec 10).

The tour counterpart of staff_actions.py: each action is listed only in the statuses its
endpoint accepts (ALLOWED_TRANSITIONS of services/tours.py), and the same refusal function the
endpoint raises with decides `allowed` and gives the `reason`. The frontend shows an allowed action
as a button, a refused one as a disabled button with the reason, and never mirrors these rules.

| action    | listed in            | refused by                                  |
|-----------|----------------------|---------------------------------------------|
| edit      | draft, active        | edit_refusal (active: unpublish first)      |
| publish   | draft                | publish_refusal (form checks, dates passed) |
| unpublish | active               | —                                           |
| archive   | draft, active        | archive_refusal (partly paid transfers)     |
| restore   | archived             | —                                           |
| copy      | every status         | —                                           |

`locked_fields` (services/tours.lock_reason) and the booking numbers the confirmation dialogs
show (`active_bookings` for unpublish, `archive_cancels` for archive) come with them.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Tour
from app.models.enums import TourAction as A
from app.models.enums import TourStatus
from app.services import tours as t


@dataclass
class TourState:
    actions: list[dict]
    locked_fields: list[dict] = field(default_factory=list)
    active_bookings: int = 0
    archive_cancels: int = 0


def tour_state(db: Session, tour: Tour) -> TourState:
    counts = t.booking_counts(db, tour.id)
    status = tour.status
    actions: list[dict] = []

    def add(action: A, listed: bool, refusal=None) -> None:
        if not listed:
            return
        reason = refusal() if refusal else None
        actions.append(dict(action=action, allowed=reason is None, reason=reason))

    allowed_next = t.ALLOWED_TRANSITIONS[status]
    add(A.EDIT, status != TourStatus.ARCHIVED, lambda: t.edit_refusal(tour))
    add(A.PUBLISH, TourStatus.ACTIVE in allowed_next, lambda: t.publish_refusal(db, tour))
    add(A.UNPUBLISH, status == TourStatus.ACTIVE)
    add(A.ARCHIVE, TourStatus.ARCHIVED in allowed_next, lambda: t.archive_refusal(counts))
    add(A.RESTORE, status == TourStatus.ARCHIVED)
    add(A.COPY, True)
    return TourState(actions=actions, locked_fields=t.locked_fields(counts),
                     active_bookings=counts["active_bookings"],
                     archive_cancels=counts["archive_cancels"])
