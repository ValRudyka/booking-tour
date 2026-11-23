"""Back-office: tour management by the manager (ТЗ 4.5.2, form 4.6.2.1, statuses 4.4.1)."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import TourStatus, UserRole
from app.schemas.common import Page
from app.schemas.tours import (ImageOrder, ManagerTourListItem, ManagerTourOut, TourCreate,
                               TourImageOut, TourUpdate)
from app.services import images as image_files
from app.services import tours as tour_service
from app.services.errors import DomainError

router = APIRouter(prefix="/manager/tours", tags=["manager: tours"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message)


def _get(db, tour_id: int):
    try:
        return tour_service.get_tour(db, tour_id)
    except DomainError as error:
        _raise(error)


@router.get("", response_model=Page[ManagerTourListItem], summary="Список турів (усі статуси)")
def list_tours(db: DbSession, _: Manager,
               status_: Annotated[TourStatus | None, Query(alias="status")] = None,
               q: Annotated[str | None, Query(max_length=100)] = None,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = tour_service.list_tours(db, status=status_, q=q, page=page, page_size=page_size)
    return Page(items=[ManagerTourListItem.model_validate(t) for t in items], total=total,
                page=page, page_size=page_size)


@router.post("", response_model=ManagerTourOut, status_code=status.HTTP_201_CREATED,
             summary="Створити тур (чернетка)")
def create_tour(data: TourCreate, db: DbSession, manager: Manager):
    try:
        tour = tour_service.create_tour(db, data.model_dump(), manager)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour


@router.get("/{tour_id}", response_model=ManagerTourOut, summary="Тур для редагування")
def get_tour(tour_id: int, db: DbSession, _: Manager):
    return _get(db, tour_id)


@router.patch("/{tour_id}", response_model=ManagerTourOut, summary="Редагувати чернетку")
def update_tour(tour_id: int, data: TourUpdate, db: DbSession, _: Manager):
    tour = _get(db, tour_id)
    try:
        tour_service.update_tour(db, tour, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour


@router.post("/{tour_id}/copy", response_model=ManagerTourOut, status_code=status.HTTP_201_CREATED,
             summary="Копіювати тур у нову чернетку")
def copy_tour(tour_id: int, db: DbSession, manager: Manager):
    new_tour = tour_service.copy_tour(db, _get(db, tour_id), manager)
    db.commit()
    return new_tour


def _change_status(tour_id: int, new_status: TourStatus, db, manager: User):
    tour = _get(db, tour_id)
    try:
        tour_service.change_status(db, tour, new_status, manager)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour


@router.post("/{tour_id}/publish", response_model=ManagerTourOut, summary="Опублікувати")
def publish(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.ACTIVE, db, manager)


@router.post("/{tour_id}/unpublish", response_model=ManagerTourOut,
             summary="Зняти з публікації (повернути в чернетку)")
def unpublish(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.DRAFT, db, manager)


@router.post("/{tour_id}/archive", response_model=ManagerTourOut, summary="Архівувати")
def archive(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.ARCHIVED, db, manager)


# ---------- photos (form 4.6.2.1, field 18)
@router.post("/{tour_id}/images", response_model=list[TourImageOut],
             status_code=status.HTTP_201_CREATED, summary="Завантажити фото (JPG/PNG)")
def upload_images(tour_id: int, db: DbSession, _: Manager,
                  files: Annotated[list[UploadFile], File(description="Один або кілька файлів")]):
    # A plain `def` endpoint runs in a thread pool, so reading UploadFile.file synchronously is fine.
    tour = _get(db, tour_id)
    try:
        images = tour_service.add_images(db, tour, [(f.file, f.filename) for f in files])
    except DomainError as error:
        _raise(error)
    db.commit()
    return images


@router.delete("/{tour_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Видалити фото")
def delete_image(tour_id: int, image_id: int, db: DbSession, _: Manager):
    tour = _get(db, tour_id)
    try:
        path = tour_service.delete_image(db, tour, image_id)
    except DomainError as error:
        _raise(error)
    db.commit()
    image_files.remove_files([path])  # only after the row is really gone


@router.put("/{tour_id}/images/order", response_model=list[TourImageOut],
            summary="Змінити порядок фото")
def reorder_images(tour_id: int, data: ImageOrder, db: DbSession, _: Manager):
    tour = _get(db, tour_id)
    try:
        tour_service.reorder_images(db, tour, data.image_ids)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour.images
