"""Back-office: moderation of reviews (ТЗ 4.5.7 step 6; the manager is the moderator, ТЗ 4.3).
Staff never edit a review — they only publish or reject it."""
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import DbSession, require_roles
from app.models import User
from app.models.enums import ReviewStatus, UserRole
from app.routers.order_views import staff_review
from app.schemas.common import Page
from app.schemas.reviews import RejectReviewIn, StaffReviewOut
from app.services import reviews as review_service
from app.services.errors import DomainError

router = APIRouter(prefix="/manager/reviews", tags=["manager: reviews"])

Manager = Annotated[User, Depends(require_roles(UserRole.MANAGER))]


def _raise(error: DomainError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from None


@router.get("", response_model=Page[StaffReviewOut], summary="Черга модерації (найстаріші спочатку)")
def list_reviews(db: DbSession, _: Manager,
                 status_: Annotated[ReviewStatus, Query(alias="status")] = ReviewStatus.PENDING,
                 tour_id: int | None = None,
                 hotel_id: int | None = None,
                 page: Annotated[int, Query(ge=1)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    items, total = review_service.list_for_moderation(db, status=status_, tour_id=tour_id,
                                                      hotel_id=hotel_id, page=page, page_size=page_size)
    return Page(items=[staff_review(r) for r in items], total=total, page=page, page_size=page_size)


@router.get("/{review_id}", response_model=StaffReviewOut, summary="Відгук з фото")
def get_review(review_id: int, db: DbSession, _: Manager):
    try:
        return staff_review(review_service.get_review(db, review_id))
    except DomainError as error:
        _raise(error)


@router.post("/{review_id}/publish", response_model=StaffReviewOut, summary="Опублікувати")
def publish(review_id: int, db: DbSession, manager: Manager):
    try:
        review = review_service.moderate_publish(db, manager, review_id)
    except DomainError as error:
        _raise(error)
    db.commit()
    return staff_review(review)


@router.post("/{review_id}/reject", response_model=StaffReviewOut,
             summary="Відхилити або зняти з публікації (потрібна причина)")
def reject(review_id: int, data: RejectReviewIn, db: DbSession, manager: Manager):
    try:
        review = review_service.moderate_reject(db, manager, review_id, data.reject_reason)
    except DomainError as error:
        _raise(error)
    db.commit()
    return staff_review(review)
