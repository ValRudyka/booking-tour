"""In-app notifications of the current user."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Page


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None
    title: str
    body: str
    is_read: bool
    created_at: datetime


class NotificationPage(Page[NotificationOut]):
    unread: int          # for the bell icon, independent of the filter


class ReadAllOut(BaseModel):
    marked: int
