"""Public site information: support contacts for the footer and «Забули пароль?»."""
from fastapi import APIRouter

from app.core.deps import DbSession
from app.schemas.site import SiteContactsOut
from app.services import settings_admin

router = APIRouter(prefix="/site", tags=["site"])


@router.get("/contacts", response_model=SiteContactsOut, summary="Контакти служби підтримки")
def contacts(db: DbSession):
    return settings_admin.support_contacts(db)
