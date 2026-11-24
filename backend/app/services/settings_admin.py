"""System administrator: global settings (ТЗ 4.5.8, form 4.6.4.1).

Values live in `settings` (key -> JSON) and `currency_rates` (EUR, USD; UAH is fixed at 1). They
are read from the database on every use, so a change applies at once to new calculations
(ТЗ 4.5.8 step 6). Prices of orders already placed never change: total_uah and rate_used are frozen
at checkout. The booking timeout applies to orders created after the change.

The payment gateway (use case «Налаштувати інтеграцію платіжних шлюзів») is shown read-only:
keys stay in backend/.env and are never stored in the database or returned by the API.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings as app_config
from app.models import CurrencyRate, Setting, User
from app.models.enums import Currency
from app.services.audit import audit, changed
from app.services.errors import DomainError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RATE_FIELDS = {"eur_rate": Currency.EUR, "usd_rate": Currency.USD}
# key: (Ukrainian label, kind, min, max)
SETTING_FIELDS: dict[str, tuple[str, str, Any, Any]] = {
    "acquiring_percent": ("Відсоток еквайрингу", "decimal2", Decimal("0"), Decimal("10")),
    "booking_timeout_min": ("Таймаут бронювання, хв", "int", 5, 120),
    "bank_transfer_hold_hours": ("Утримання місць при переказі, год", "int", 1, 168),
    "review_premoderation": ("Премодерація відгуків", "bool", None, None),
    "system_email": ("Системний e-mail", "email", None, None),
    "maintenance_mode": ("Технічні роботи", "bool", None, None),
}
DEFAULTS = {"acquiring_percent": Decimal("2.5"), "booking_timeout_min": 20, "bank_transfer_hold_hours": 48,
            "review_premoderation": True, "system_email": "", "maintenance_mode": False}


def _read(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    value = DEFAULTS[key] if row is None or row.value is None else row.value
    kind = SETTING_FIELDS[key][1]
    return Decimal(str(value)) if kind == "decimal2" else value


def current(db: Session) -> dict[str, Any]:
    values: dict[str, Any] = {name: db.get(CurrencyRate, cur).rate_to_uah for name, cur in RATE_FIELDS.items()}
    values.update({key: _read(db, key) for key in SETTING_FIELDS})
    return values


def changes_info(db: Session) -> dict[str, dict[str, Any]]:
    """When and by whom each value was last changed."""
    info = {name: {"updated_at": r.updated_at, "updated_by": r.updated_by}
            for name, cur in RATE_FIELDS.items() if (r := db.get(CurrencyRate, cur))}
    for key in SETTING_FIELDS:
        row = db.get(Setting, key)
        if row is not None:
            info[key] = {"updated_at": row.updated_at, "updated_by": row.updated_by}
    return info


def _decimal(value: Any, label: str, places: int, low: Decimal, high: Decimal) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise DomainError(f"«{label}»: потрібне число", 422) from None
    if not number.is_finite() or not low <= number <= high:
        raise DomainError(f"«{label}»: від {low} до {high}", 422)
    if -number.as_tuple().exponent > places:
        raise DomainError(f"«{label}»: не більше {places} знаків після коми", 422)
    return number


def _validate(changes: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for name in RATE_FIELDS:
        if name in changes:
            clean[name] = _decimal(changes[name], f"Курс {name[:3].upper()}", 4, Decimal("0.0001"), Decimal("10000"))
    for key, (label, kind, low, high) in SETTING_FIELDS.items():
        if key not in changes:
            continue
        value = changes[key]
        if kind == "decimal2":
            clean[key] = _decimal(value, label, 2, low, high)
        elif kind == "int":
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise DomainError(f"«{label}»: ціле число від {low} до {high}", 422)
            clean[key] = value
        elif kind == "bool":
            if not isinstance(value, bool):
                raise DomainError(f"«{label}»: так або ні", 422)
            clean[key] = value
        else:
            email = (value or "").strip().lower()
            if not EMAIL_RE.match(email) or len(email) > 255:
                raise DomainError(f"«{label}»: некоректна адреса", 422)
            clean[key] = email
    return clean


def update(db: Session, admin: User, changes: dict[str, Any]) -> dict[str, Any]:
    """Form 4.6.4.1 «Зберегти налаштування»: only the fields that were sent change; everything is
    validated first, then saved in one transaction with one audit row."""
    clean = _validate({k: v for k, v in changes.items() if v is not None})
    before = current(db)
    for name, value in clean.items():
        if name in RATE_FIELDS:
            rate = db.get(CurrencyRate, RATE_FIELDS[name])
            if rate.rate_to_uah != value:
                rate.rate_to_uah, rate.updated_by = value, admin.id
            continue
        if before[name] == value:
            continue
        row = db.get(Setting, name) or Setting(key=name)
        # JSONB has no decimal type: the percent is kept as a JSON number (2 places).
        row.value = float(value) if isinstance(value, Decimal) else value
        row.updated_by = admin.id
        db.add(row)
    db.flush()
    after = current(db)
    old, new = changed(before, after)
    if new:
        audit(db, admin, "settings", "global", "updated", old, new)
    return after


def gateway_status() -> dict[str, Any]:
    """What is configured, never the values themselves."""
    from app.services.payments.gateway import gateway_name

    key = app_config.stripe_secret_key or ""
    mode = "test" if key.startswith(("sk_test_", "rk_test_")) else "live" if key.startswith(("sk_live_", "rk_live_")) \
        else None
    return {"gateway": gateway_name(), "stripe_key_configured": bool(key), "stripe_key_mode": mode,
            "webhook_secret_configured": bool(app_config.stripe_webhook_secret),
            "stripe_api_version": app_config.stripe_api_version,
            "how_to_change": "Ключі задаються в backend/.env (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, "
                             "PAYMENT_GATEWAY) і не зберігаються в базі даних; після зміни перезапустіть сервер."}
