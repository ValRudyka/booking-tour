"""«Сповіщення»: in-app notifications of the logged-in user (any role)."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.notifications import NotificationOut, NotificationPage, ReadAllOut
from app.services import notifications as service
from app.services.errors import DomainError

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage, summary="Мої сповіщення (нові спочатку)")
def list_notifications(db: DbSession, user: CurrentUser, unread_only: bool = False,
                       page: Annotated[int, Query(ge=1)] = 1,
                       page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total, unread = service.list_own(db, user, unread_only, page, page_size)
    return NotificationPage(items=[NotificationOut.model_validate(n) for n in items], total=total,
                            page=page, page_size=page_size, unread=unread)


@router.post("/read-all", response_model=ReadAllOut, summary="Позначити всі як прочитані")
def read_all(db: DbSession, user: CurrentUser):
    marked = service.mark_all_read(db, user)
    db.commit()
    return ReadAllOut(marked=marked)


@router.post("/{notification_id}/read", response_model=NotificationOut,
             summary="Позначити сповіщення як прочитане")
def read_one(notification_id: int, db: DbSession, user: CurrentUser):
    try:
        note = service.mark_read(db, user, notification_id)
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    db.commit()
    return NotificationOut.model_validate(note)
