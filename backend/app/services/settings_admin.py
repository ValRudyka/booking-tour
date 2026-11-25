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
from app.schemas.auth import normalize_phone
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
    # Fields 8–9 (feature/frontend-auth): how clients reach support, e.g. to reset a password.
    # Public through GET /api/site/contacts; empty = not shown.
    "support_phone": ("Телефон підтримки", "phone_or_empty", None, None),
    "support_email": ("E-mail підтримки", "email_or_empty", None, None),
    # Spec 13 §3: the contacts page and the footer show the address; the maintenance 503 shows
    # the message (empty = the default text, maintenance.MESSAGE). max = text length.
    "support_address": ("Адреса офісу", "text_or_empty", None, 300),
    "maintenance_message": ("Повідомлення для відвідувачів", "text_or_empty", None, 500),
}
DEFAULTS = {"acquiring_percent": Decimal("2.5"), "booking_timeout_min": 20, "bank_transfer_hold_hours": 48,
            "review_premoderation": True, "system_email": "", "maintenance_mode": False,
            "support_phone": "", "support_email": "", "support_address": "", "maintenance_message": ""}


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
    """When and by whom each value was last changed (the name for the settings page)."""
    info = {name: {"updated_at": r.updated_at, "updated_by": r.updated_by}
            for name, cur in RATE_FIELDS.items() if (r := db.get(CurrencyRate, cur))}
    for key in SETTING_FIELDS:
        row = db.get(Setting, key)
        if row is not None:
            info[key] = {"updated_at": row.updated_at, "updated_by": row.updated_by}
    for change in info.values():
        author = db.get(User, change["updated_by"]) if change["updated_by"] is not None else None
        change["updated_by_name"] = f"{author.last_name} {author.first_name}" if author else None
    return info


RATE_RULE = {"min": Decimal("0.0001"), "max": Decimal("10000"), "places": 4}


def rules() -> dict[str, dict[str, Any]]:
    """Limits the settings form shows (the same values _validate() checks)."""
    out: dict[str, dict[str, Any]] = {name: dict(RATE_RULE) for name in RATE_FIELDS}
    for key, (_label, kind, low, high) in SETTING_FIELDS.items():
        if kind == "decimal2":
            out[key] = {"min": low, "max": high, "places": 2}
        elif kind == "int":
            out[key] = {"min": low, "max": high, "places": 0}
        elif kind == "text_or_empty":
            out[key] = {"max_length": high}
        elif kind in ("email", "email_or_empty"):
            out[key] = {"max_length": 255}
    return out


def limits() -> dict[str, int]:
    """Values kept in backend/.env, shown read-only on the settings page."""
    return {"max_review_photos": app_config.max_review_photos,
            "max_review_photo_mb": app_config.max_review_photo_mb}


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
            clean[name] = _decimal(changes[name], f"Курс {name[:3].upper()}", 4, RATE_RULE["min"], RATE_RULE["max"])
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
        elif kind == "text_or_empty":
            text = " ".join(str(value or "").split())          # one line, no double spaces
            if len(text) > high:
                raise DomainError(f"«{label}»: не довше {high} символів", 422)
            clean[key] = text
        elif kind == "phone_or_empty":
            phone = str(value or "").strip()
            if phone:
                try:
                    phone = normalize_phone(phone)
                except ValueError:
                    raise DomainError(f"«{label}»: у міжнародному форматі, наприклад +380441234567", 422) from None
            clean[key] = phone
        else:
            email = str(value or "").strip().lower()
            if kind == "email_or_empty" and not email:
                clean[key] = ""
                continue
            if not EMAIL_RE.match(email) or len(email) > 255:
                raise DomainError(f"«{label}»: некоректна адреса", 422)
            clean[key] = email
    return clean


def support_contacts(db: Session) -> dict[str, str | None]:
    """Public: the support phone, e-mail and office address (None when the admin has not set them)."""
    return {"phone": _read(db, "support_phone") or None, "email": _read(db, "support_email") or None,
            "address": _read(db, "support_address") or None}


def maintenance_message(db: Session) -> str | None:
    return _read(db, "maintenance_message") or None


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
