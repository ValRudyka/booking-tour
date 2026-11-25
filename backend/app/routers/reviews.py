"""Reviews (ТЗ 4.5.7, form 4.6.1.4): the client writes and corrects them; photos are private files
served with an access check."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import DbSession, OptionalUser, require_roles
from app.models import User
from app.models.enums import NameDisplay, UserRole
from app.routers.order_views import my_review, public_review
from app.schemas.common import Page
from app.schemas.orders import UploadLimitsOut
from app.schemas.reviews import MyReviewOut, OrderReviewOut, PublicReviewOut
from app.services import orders as order_service
from app.services import private_files
from app.services import reviews as review_service
from app.services.app_settings import review_premoderation
from app.services.errors import DomainError

router = APIRouter(tags=["reviews"])

Client = Annotated[User, Depends(require_roles(UserRole.CLIENT))]
Photos = Annotated[list[UploadFile] | None, File(description="Фото JPG або PNG (до 10)")]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


def _files(photos: list[UploadFile] | None):
    return [(f.file, f.filename) for f in photos or []]


@router.get("/orders/{order_id}/review", response_model=OrderReviewOut,
            summary="Відгук до замовлення (якщо є) і правила форми 4.6.1.4")
def order_review(order_id: int, db: DbSession, client: Client):
    try:
        order = order_service.get_own_order(db, client, order_id)
    except DomainError as error:
        _raise(error)
    review = review_service.review_of_order(db, order)
    return OrderReviewOut(
        can_write=review_service.review_refusal(db, order) is None,
        premoderation=review_premoderation(db),
        photos=UploadLimitsOut(**review_service.photo_limits()),
        review=my_review(review) if review else None)


@router.post("/orders/{order_id}/review", response_model=MyReviewOut, status_code=status.HTTP_201_CREATED,
             summary="Залишити відгук про завершену подорож (форма 4.6.1.4)")
def create_review(order_id: int, db: DbSession, client: Client,
                  hotel_rating: Annotated[int, Form(description="Оцінка готелю 1–5")],
                  service_rating: Annotated[int, Form(description="Оцінка сервісу 1–5")],
                  positive: Annotated[str | None, Form(description="Позитивні враження")] = None,
                  negative: Annotated[str | None, Form(description="Негативні враження")] = None,
                  name_display: Annotated[NameDisplay, Form(description="full | short | anonymous")]
                  = NameDisplay.SHORT,
                  photos: Photos = None):
    try:
        order = order_service.get_own_order(db, client, order_id)
        review = review_service.create_review(
            db, client, order, dict(hotel_rating=hotel_rating, service_rating=service_rating,
                                    positive=positive, negative=negative, name_display=name_display),
            _files(photos))
    except DomainError as error:
        _raise(error)
    db.commit()
    return my_review(review)


@router.get("/me/reviews", response_model=Page[MyReviewOut], summary="Мої відгуки і статус модерації")
def my_reviews(db: DbSession, client: Client,
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=50)] = 20):
    items, total = review_service.list_own(db, client, page, page_size)
    return Page(items=[my_review(r) for r in items], total=total, page=page, page_size=page_size)


@router.patch("/me/reviews/{review_id}", response_model=MyReviewOut,
              summary="Виправити відхилений відгук і подати знову (один раз)")
def resubmit_review(review_id: int, db: DbSession, client: Client,
                    hotel_rating: Annotated[int | None, Form()] = None,
                    service_rating: Annotated[int | None, Form()] = None,
                    positive: Annotated[str | None, Form()] = None,
                    negative: Annotated[str | None, Form()] = None,
                    name_display: Annotated[NameDisplay | None, Form()] = None,
                    clear_photos: Annotated[bool, Form(description="Прибрати всі фото")] = False,
                    photos: Photos = None):
    # Only the fields that were sent change; new photos replace all old ones.
    sent = dict(hotel_rating=hotel_rating, service_rating=service_rating, positive=positive,
                negative=negative, name_display=name_display)
    try:
        review, old_files = review_service.resubmit(
            db, client, review_id, {k: v for k, v in sent.items() if v is not None},
            _files(photos), clear_photos)
    except DomainError as error:
        _raise(error)
    db.commit()
    for path in old_files:                    # only after the new state is saved
        private_files.remove(path)
    return my_review(review)


@router.get("/reviews/{review_id}/photos/{photo_id}", summary="Фото відгуку",
            responses={404: {"description": "Немає такого фото або відгук не опубліковано"}})
def review_photo(review_id: int, photo_id: int, db: DbSession, viewer: OptionalUser):
    """Published review: anyone. Pending / rejected: only the author and managers; others get
    404, so a guest cannot even learn that such a review exists."""
    try:
        path, media_type, public = review_service.photo_file(db, review_id, photo_id, viewer)
    except DomainError as error:
        _raise(error)
    cache = "public, max-age=86400" if public else "private, no-store"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": cache})


# ---------- public, no login: published reviews only, no personal data
@router.get("/tours/{tour_id}/reviews", response_model=Page[PublicReviewOut],
            summary="Відгуки про тур (опубліковані, нові спочатку)")
def tour_reviews(tour_id: int, db: DbSession,
                 page: Annotated[int, Query(ge=1)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    try:
        items, total = review_service.public_reviews(db, tour_id=tour_id, page=page, page_size=page_size)
    except DomainError as error:
        _raise(error)
    return Page(items=[public_review(r) for r in items], total=total, page=page, page_size=page_size)


@router.get("/hotels/{hotel_id}/reviews", response_model=Page[PublicReviewOut],
            summary="Відгуки про готель (опубліковані, нові спочатку)")
def hotel_reviews(hotel_id: int, db: DbSession,
                  page: Annotated[int, Query(ge=1)] = 1,
                  page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    try:
        items, total = review_service.public_reviews(db, hotel_id=hotel_id, page=page, page_size=page_size)
    except DomainError as error:
        _raise(error)
    return Page(items=[public_review(r) for r in items], total=total, page=page, page_size=page_size)
