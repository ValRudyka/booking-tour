"""Audit log (ТЗ 5.9: history of changes for accountability; ТЗ 7: the log is protected from
changes — the table is append-only, enforced by a database trigger).

audit() writes who changed what with the old and new values, made JSON-safe. Fields whose name
looks secret (password, secret, key, token, hash) are never written.
"""
import enum
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User

SECRET_PARTS = ("password", "secret", "key", "token", "hash")


def _safe(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return clean(value)
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def clean(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    return {k: _safe(v) for k, v in values.items() if not any(p in k.lower() for p in SECRET_PARTS)}


def snapshot(obj: Any, fields: list[str] | tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def changed(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the fields whose value changed: (old values, new values)."""
    keys = [k for k in new if old.get(k) != new[k]]
    return {k: old.get(k) for k in keys}, {k: new[k] for k in keys}


def audit(db: Session, user: User | None, entity: str, entity_id: Any, action: str,
          old: dict[str, Any] | None = None, new: dict[str, Any] | None = None) -> AuditLog:
    entry = AuditLog(user_id=user.id if user else None, entity=entity, entity_id=str(entity_id),
                     action=action, old_value=clean(old), new_value=clean(new))
    db.add(entry)
    db.flush()
    return entry


def list_entries(db: Session, *, user_id: int | None, entity: str | None, entity_id: str | None,
                 action: str | None, date_from: datetime | None, date_to: datetime | None,
                 page: int, page_size: int) -> tuple[list[AuditLog], int]:
    query = select(AuditLog)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if date_from is not None:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.where(AuditLog.created_at < date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total
