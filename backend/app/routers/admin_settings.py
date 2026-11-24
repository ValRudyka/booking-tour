"""System administrator: global settings (form 4.6.4.1), payment gateway status and the audit
log (ТЗ 4.5.8, 5.9, 7). Role admin only."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.admin import AuditLogOut, GatewayStatusOut, SettingsIn, SettingsOut
from app.schemas.common import Page
from app.services import audit as audit_service
from app.services import settings_admin as service
from app.services.errors import DomainError

router = APIRouter(prefix="/admin", tags=["admin: settings and audit"])

Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _out(db) -> SettingsOut:
    return SettingsOut(**service.current(db), changes=service.changes_info(db))


@router.get("/settings", response_model=SettingsOut, summary="Глобальні налаштування (форма 4.6.4.1)")
def get_settings(db: DbSession, _: Admin):
    return _out(db)


@router.put("/settings", response_model=SettingsOut,
            summary="Зберегти налаштування (змінюються лише передані поля)")
def update_settings(data: SettingsIn, db: DbSession, admin: Admin):
    try:
        service.update(db, admin, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return _out(db)


@router.get("/payment-gateway", response_model=GatewayStatusOut,
            summary="Платіжний шлюз: що налаштовано (без ключів)")
def payment_gateway(_: Admin):
    return service.gateway_status()


@router.get("/audit-log", response_model=Page[AuditLogOut], summary="Журнал змін (нові спочатку)")
def audit_log(db: DbSession, _: Admin,
              user_id: int | None = None,
              entity: Annotated[str | None, Query(max_length=50, description="user, settings, hotel, promo_code…")] = None,
              entity_id: Annotated[str | None, Query(max_length=50)] = None,
              action: Annotated[str | None, Query(max_length=50)] = None,
              date_from: date | None = None,
              date_to: Annotated[date | None, Query(description="Включно")] = None,
              page: Annotated[int, Query(ge=1)] = 1,
              page_size: Annotated[int, Query(ge=1, le=100)] = 50):
    start = datetime.combine(date_from, time.min, timezone.utc) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc) if date_to else None
    items, total = audit_service.list_entries(db, user_id=user_id, entity=entity, entity_id=entity_id,
                                              action=action, date_from=start, date_to=end, page=page,
                                              page_size=page_size)
    return Page(items=[AuditLogOut.model_validate(e) for e in items], total=total, page=page,
                page_size=page_size)
