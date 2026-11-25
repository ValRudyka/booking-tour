"""Back-office: tour management by the manager (ТЗ 4.5.2, form 4.6.2.1, statuses 4.4.1, spec 10)."""
from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.config import settings
from app.core.deps import DbSession, require_roles
from app.models import Tour, User
from app.models.enums import ManagerTourSort, TourStatus, UserRole
from app.schemas.common import Page
from app.schemas.orders import UploadLimitsOut
from app.schemas.tours import (ImageOrder, ManagerTourHotelOut, ManagerTourListItem, ManagerTourOut,
                               TourCopyIn, TourCreate, TourImageOut, TourRulesOut, TourUpdate)
from app.services import catalog, clock, text_lists
from app.services import images as image_files
from app.services import tours as tour_service
from app.services.errors import DomainError
from app.services.images import SIGNATURES
from app.services.seats import free_seats
from app.services.tour_actions import tour_state

router = APIRouter(prefix="/manager/tours", tags=["manager: tours"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(error: DomainError) -> NoReturn:
    if error.loc is not None:
        # A rule about one form field: FastAPI's own 422 shape, so the editor shows the message
        # under that field. "tour_rule" tells the frontend msg is a Ukrainian text to show as is.
        raise HTTPException(status_code=error.status_code, detail=[
            {"loc": list(error.loc), "msg": error.message, "type": "tour_rule"}]) from None
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _get(db, tour_id: int) -> Tour:
    try:
        return tour_service.get_tour(db, tour_id)
    except DomainError as error:
        _raise(error)


class _View:
    """The tour row plus computed values, read by the response models with from_attributes."""

    def __init__(self, tour: Tour, **extra):
        self._tour = tour
        self.__dict__.update(extra)

    def __getattr__(self, name):
        return getattr(self._tour, name)


def _state(db, tour: Tour) -> dict:
    state = tour_state(db, tour)
    return dict(tour_actions=state.actions, locked_fields=state.locked_fields,
                active_bookings=state.active_bookings, archive_cancels=state.archive_cancels,
                for_sale=catalog.is_for_sale(tour))


def _hotel(tour: Tour) -> ManagerTourHotelOut:
    hotel = tour.hotel
    resort = hotel.resort
    country = resort.country
    return ManagerTourHotelOut(id=hotel.id, name=hotel.name, stars=hotel.stars, resort_id=resort.id,
                               resort_name=resort.name_uk, country_id=country.id,
                               country_name=country.name_uk,
                               is_archived=hotel.is_archived or resort.is_archived or country.is_archived)


def tour_out(db, tour: Tour) -> ManagerTourOut:
    db.refresh(tour, ["images", "program_days"])     # after a copy, reorder or a new program
    return ManagerTourOut.model_validate(_View(
        tour, hotel=_hotel(tour), seats_held=tour_service.seats_held(db, tour.id), **_state(db, tour)))


def _list_item(db, tour: Tour) -> ManagerTourListItem:
    hotel = tour.hotel
    return ManagerTourListItem.model_validate(_View(
        tour, hotel_name=hotel.name, resort_name=hotel.resort.name_uk,
        country_name=hotel.resort.country.name_uk,
        image_url=f"/uploads/{tour.images[0].file_path}" if tour.images else None,
        nearest_start=tour_service.nearest_start(tour),
        free_seats=free_seats(db, tour.id, clock.now()), **_state(db, tour)))


@router.get("", response_model=Page[ManagerTourListItem], summary="Список турів (усі статуси)")
def list_tours(db: DbSession, _: Manager,
               status_: Annotated[TourStatus | None, Query(alias="status")] = None,
               q: Annotated[str | None, Query(max_length=100)] = None,
               country_id: int | None = None, resort_id: int | None = None,
               departure_from: Annotated[date | None, Query(description="Період виїзду: від")] = None,
               departure_to: Annotated[date | None, Query(description="Період виїзду: до")] = None,
               sort: ManagerTourSort = ManagerTourSort.UPDATED_DESC,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = tour_service.list_tours(
        db, status=status_, q=q, country_id=country_id, resort_id=resort_id,
        departure_from=departure_from, departure_to=departure_to, sort=sort, page=page,
        page_size=page_size)
    return Page(items=[_list_item(db, t) for t in items], total=total, page=page, page_size=page_size)


# Declared before /{tour_id}.
@router.get("/rules", response_model=TourRulesOut, summary="Обмеження форми туру (фото, тексти)")
def rules(_: Manager):
    return TourRulesOut(
        photos=UploadLimitsOut(max_files=settings.max_images_per_tour, max_file_mb=settings.max_image_mb,
                               file_types=sorted(set(SIGNATURES.values()))),
        max_title=tour_service.MAX_TITLE, max_description=tour_service.MAX_DESCRIPTION,
        max_day_text=tour_service.MAX_DAY_TEXT, min_nights=tour_service.MIN_NIGHTS,
        max_nights=tour_service.MAX_NIGHTS, max_list_items=text_lists.MAX_ITEMS,
        max_list_item_length=text_lists.MAX_ITEM_LENGTH)


@router.post("", response_model=ManagerTourOut, status_code=status.HTTP_201_CREATED,
             summary="Створити тур (чернетка)")
def create_tour(data: TourCreate, db: DbSession, manager: Manager):
    try:
        tour = tour_service.create_tour(db, data.model_dump(), manager)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour_out(db, tour)


@router.get("/{tour_id}", response_model=ManagerTourOut, summary="Тур для редагування")
def get_tour(tour_id: int, db: DbSession, _: Manager):
    return tour_out(db, _get(db, tour_id))


@router.patch("/{tour_id}", response_model=ManagerTourOut, summary="Редагувати чернетку")
def update_tour(tour_id: int, data: TourUpdate, db: DbSession, _: Manager):
    tour = _get(db, tour_id)
    try:
        tour = tour_service.update_tour(db, tour, data.model_dump(exclude_unset=True))
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour_out(db, tour)


@router.post("/{tour_id}/copy", response_model=ManagerTourOut, status_code=status.HTTP_201_CREATED,
             summary="Копіювати тур у нову чернетку з новими датами")
def copy_tour(tour_id: int, data: TourCopyIn, db: DbSession, manager: Manager):
    try:
        new_tour = tour_service.copy_tour(db, _get(db, tour_id), manager,
                                          data.departure_from, data.departure_to)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour_out(db, new_tour)


def _change_status(tour_id: int, new_status: TourStatus, db, manager: User,
                   from_status: TourStatus | None = None):
    tour = _get(db, tour_id)
    try:
        tour = tour_service.change_status(db, tour, new_status, manager, from_status)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour_out(db, tour)


@router.post("/{tour_id}/publish", response_model=ManagerTourOut, summary="Опублікувати")
def publish(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.ACTIVE, db, manager)


@router.post("/{tour_id}/unpublish", response_model=ManagerTourOut,
             summary="Зняти з публікації (повернути в чернетку; бронювання лишаються)")
def unpublish(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.DRAFT, db, manager, TourStatus.ACTIVE)


@router.post("/{tour_id}/archive", response_model=ManagerTourOut,
             summary="Архівувати (неоплачені бронювання скасовуються)")
def archive(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.ARCHIVED, db, manager)


@router.post("/{tour_id}/restore", response_model=ManagerTourOut,
             summary="Відновити з архіву (у чернетку)")
def restore(tour_id: int, db: DbSession, manager: Manager):
    return _change_status(tour_id, TourStatus.DRAFT, db, manager, TourStatus.ARCHIVED)


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
            summary="Змінити порядок фото (перше — головне)")
def reorder_images(tour_id: int, data: ImageOrder, db: DbSession, _: Manager):
    tour = _get(db, tour_id)
    try:
        tour_service.reorder_images(db, tour, data.image_ids)
    except DomainError as error:
        _raise(error)
    db.commit()
    return tour.images
