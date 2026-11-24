"""System administrator: reference data (ТЗ 4.3, 4.5.8). Role admin only.

The same endpoints for every table (built in a loop below):
    GET    /api/admin/{kind}                    list (archived too; ?archived=, ?parent_id=)
    POST   /api/admin/{kind}                    create
    PATCH  /api/admin/{kind}/{id}               edit
    POST   /api/admin/{kind}/{id}/archive       hide from public lists and new tours/orders
    POST   /api/admin/{kind}/{id}/restore
    DELETE /api/admin/{kind}/{id}               only if nothing refers to it
kind = countries | cities | resorts | hotels | insurance-types | transfer-types.
Languages (form 4.6.4.1, field 5) have their own small set: /api/admin/languages[/{code}].
"""
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas import admin as s
from app.services import reference_admin as service
from app.services.errors import DomainError

router = APIRouter(prefix="/admin", tags=["admin: reference data"])

Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]

SCHEMAS: dict[str, tuple[type[BaseModel], type[BaseModel], type[BaseModel]]] = {
    "countries": (s.CountryIn, s.CountryPatch, s.CountryAdminOut),
    "cities": (s.CityIn, s.CityPatch, s.CityAdminOut),
    "resorts": (s.ResortIn, s.ResortPatch, s.ResortAdminOut),
    "hotels": (s.HotelIn, s.HotelPatch, s.HotelAdminOut),
    "insurance-types": (s.ServiceTypeIn, s.ServiceTypePatch, s.ServiceTypeAdminOut),
    "transfer-types": (s.ServiceTypeIn, s.ServiceTypePatch, s.ServiceTypeAdminOut),
}


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _run(db, action) -> Any:
    try:
        result = action()
    except DomainError as error:
        _raise(error)
    db.commit()
    return result


def _add_routes(kind: str, create_in: type[BaseModel], patch_in: type[BaseModel], out: type[BaseModel]) -> None:
    label = service.KINDS[kind].label

    @router.get(f"/{kind}", response_model=list[out], summary=f"{label}: список", name=f"list_{kind}")
    def list_items(db: DbSession, _: Admin, archived: bool | None = None,
                   parent_id: Annotated[int | None, Query(description="Країна / курорт")] = None):
        return service.list_items(db, kind, archived, parent_id)

    @router.post(f"/{kind}", response_model=out, status_code=status.HTTP_201_CREATED,
                 summary=f"{label}: створити", name=f"create_{kind}")
    def create_item(data: create_in, db: DbSession, admin: Admin):  # type: ignore[valid-type]
        return _run(db, lambda: service.create_item(db, admin, kind, data.model_dump()))

    @router.patch(f"/{kind}/{{item_id}}", response_model=out, summary=f"{label}: редагувати",
                  name=f"update_{kind}")
    def update_item(item_id: int, data: patch_in, db: DbSession, admin: Admin):  # type: ignore[valid-type]
        return _run(db, lambda: service.update_item(db, admin, kind, item_id,
                                                    data.model_dump(exclude_unset=True)))

    @router.post(f"/{kind}/{{item_id}}/archive", response_model=out, summary=f"{label}: архівувати",
                 name=f"archive_{kind}")
    def archive_item(item_id: int, db: DbSession, admin: Admin):
        return _run(db, lambda: service.set_archived(db, admin, kind, item_id, True))

    @router.post(f"/{kind}/{{item_id}}/restore", response_model=out, summary=f"{label}: відновити",
                 name=f"restore_{kind}")
    def restore_item(item_id: int, db: DbSession, admin: Admin):
        return _run(db, lambda: service.set_archived(db, admin, kind, item_id, False))

    @router.delete(f"/{kind}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT,
                   summary=f"{label}: видалити (лише якщо ніде не використовується)", name=f"delete_{kind}")
    def delete_item(item_id: int, db: DbSession, admin: Admin):
        _run(db, lambda: service.delete_item(db, admin, kind, item_id))


for _kind, (_create, _patch, _out) in SCHEMAS.items():
    _add_routes(_kind, _create, _patch, _out)


# ---------- languages
@router.get("/languages", response_model=list[s.LanguageOut], summary="Мови сайту")
def list_languages(db: DbSession, _: Admin):
    return service.list_languages(db)


@router.post("/languages", response_model=s.LanguageOut, status_code=status.HTTP_201_CREATED,
             summary="Додати мову")
def create_language(data: s.LanguageIn, db: DbSession, admin: Admin):
    return _run(db, lambda: service.create_language(db, admin, data.code, data.name, data.is_enabled))


@router.patch("/languages/{code}", response_model=s.LanguageOut, summary="Назва / увімкнена")
def update_language(code: str, data: s.LanguagePatch, db: DbSession, admin: Admin):
    return _run(db, lambda: service.update_language(db, admin, code, data.model_dump(exclude_unset=True)))


@router.delete("/languages/{code}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити мову")
def delete_language(code: str, db: DbSession, admin: Admin):
    _run(db, lambda: service.delete_language(db, admin, code))
