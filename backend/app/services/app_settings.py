"""Global settings stored in the `settings` table by the admin (ТЗ form 4.6.4.1)."""
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULT_BOOKING_TIMEOUT_MIN = 20


def get_setting(db: Session, key: str, default: Any) -> Any:
    row = db.get(Setting, key)
    return default if row is None or row.value is None else row.value


def booking_timeout_min(db: Session) -> int:
    """Form 4.6.4.1, field 4: how long checkout / awaiting_payment holds the seats."""
    return int(get_setting(db, "booking_timeout_min", DEFAULT_BOOKING_TIMEOUT_MIN))
