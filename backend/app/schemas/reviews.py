"""Review schemas (form 4.6.1.4). Public schemas carry no personal data: no user ids, phones,
e-mails or order numbers — only the author name chosen by the client."""
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import NameDisplay, ReviewStatus
from app.schemas.orders import UploadLimitsOut


class ReviewPhotoOut(BaseModel):
    id: int
    url: str               # /api/reviews/{id}/photos/{photo_id} (access checked there)


class ReviewContent(BaseModel):
    hotel_rating: int      # field 2, 1–5
    service_rating: int    # field 3, 1–5
    positive: str | None   # field 4
    negative: str | None   # field 5
    photos: list[ReviewPhotoOut]


class PublicReviewOut(ReviewContent):
    id: int
    author: str            # field 7: «Олена Коваль» / «Олена К.» / «Анонімний мандрівник»
    tour_id: int
    tour_title_uk: str
    hotel_name: str
    trip_month: str        # «2027-06»: when the trip was, without the order
    published_at: datetime | None


class MyReviewOut(ReviewContent):
    id: int
    order_id: int
    tour_id: int
    tour_title_uk: str
    hotel_name: str
    name_display: NameDisplay
    author: str            # how the name will be shown
    status: ReviewStatus
    reject_reason: str | None
    can_resubmit: bool     # rejected and not corrected yet
    submitted_at: datetime
    moderated_at: datetime | None
    created_at: datetime


class StaffReviewOut(MyReviewOut):
    """For the moderator: who wrote it and for which order."""
    order_number: str
    hotel_id: int
    user_id: int
    author_full_name: str
    moderated_by: int | None
    resubmitted_at: datetime | None


class RejectReviewIn(BaseModel):
    reject_reason: str


class OrderReviewOut(BaseModel):
    """GET /orders/{id}/review: the review of this order (if any) and what the form needs."""
    can_write: bool                # the trip took place and there is no review yet
    premoderation: bool            # setting review_premoderation: published after moderation
    photos: UploadLimitsOut        # form 4.6.1.4, field 6 (MAX_REVIEW_PHOTOS, MAX_REVIEW_PHOTO_MB)
    review: MyReviewOut | None
