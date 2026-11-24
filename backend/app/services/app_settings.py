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


DEFAULT_BANK_TRANSFER_HOLD_HOURS = 48


def bank_transfer_hold_hours(db: Session) -> int:
    """How long the seats stay held after the client chooses a bank transfer
    (and again after each partial transfer): a transfer takes days, not minutes."""
    return int(get_setting(db, "bank_transfer_hold_hours", DEFAULT_BANK_TRANSFER_HOLD_HOURS))


def review_premoderation(db: Session) -> bool:
    """ТЗ 4.5.7 step 6: new reviews wait for moderation (true, default) or appear at once."""
    return bool(get_setting(db, "review_premoderation", True))
