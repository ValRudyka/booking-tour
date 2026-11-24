"""Reviews of trips (ТЗ 4.5.7, form 4.6.1.4): written by the client after the trip, moderated by
a manager, shown publicly when published; the hotel rating comes from published reviews.

Life cycle: pending -> published | rejected; published -> rejected (unpublish, e.g. after a
complaint); rejected -> pending once (the client corrects and resubmits it). Staff never edit the
content of a review — they only publish or reject it. With the setting review_premoderation off
(ТЗ 4.5.7 step 6) a new review is published at once by the System (moderated_by = NULL).
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Hotel, Order, OrderStatusHistory, Review, ReviewPhoto, User
from app.models.enums import NameDisplay, OrderStatus, ReviewStatus
from app.services import private_files
from app.services.app_settings import review_premoderation
from app.services.errors import DomainError

MAX_TEXT = 2000
MAX_REASON = 1000
ANONYMOUS = "Анонімний мандрівник"
JPG_PNG = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}
STATUS_LABELS = {ReviewStatus.PENDING: "на модерації", ReviewStatus.PUBLISHED: "опубліковано",
                 ReviewStatus.REJECTED: "відхилено"}

FileUpload = tuple[BinaryIO, str | None]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def author_name(review: Review) -> str:
    """Form 4.6.1.4, field 7: «Олена Коваль» / «Олена К.» / «Анонімний мандрівник»."""
    user = review.author
    if review.name_display == NameDisplay.FULL:
        return f"{user.first_name} {user.last_name}"
    if review.name_display == NameDisplay.SHORT:
        return f"{user.first_name} {user.last_name[:1]}."
    return ANONYMOUS


def can_resubmit(review: Review) -> bool:
    return review.status == ReviewStatus.REJECTED and review.resubmitted_at is None


# ---------- validation
def _rating(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise DomainError(f"{label}: оцінка від 1 до 5", 422)
    return value


def _text(value: str | None, label: str) -> str | None:
    """Both impressions are optional (form 4.6.1.4, fields 4–5)."""
    value = (value or "").strip() or None
    if value and len(value) > MAX_TEXT:
        raise DomainError(f"«{label}» — не довше {MAX_TEXT} символів", 422)
    return value


def _apply(review: Review, data: dict[str, Any]) -> None:
    if "hotel_rating" in data:
        review.hotel_rating = _rating(data["hotel_rating"], "Оцінка готелю")
    if "service_rating" in data:
        review.service_rating = _rating(data["service_rating"], "Оцінка сервісу")
    if "positive" in data:
        review.positive = _text(data["positive"], "Позитивні враження")
    if "negative" in data:
        review.negative = _text(data["negative"], "Негативні враження")
    if data.get("name_display") is not None:
        review.name_display = data["name_display"]


def _save_photos(db: Session, review: Review, files: list[FileUpload]) -> list[str]:
    """All or nothing; returns the stored paths (removed by the caller if the change fails)."""
    if len(files) > settings.max_review_photos:
        raise DomainError(f"До відгуку можна додати не більше {settings.max_review_photos} фото", 422)
    saved: list[str] = []
    try:
        for source, filename in files:
            saved.append(private_files.save_private(
                f"reviews/{review.id}", source, filename, allowed=JPG_PNG,
                max_mb=settings.max_review_photo_mb,
                wrong_type="Файл «{name}»: фото має бути JPG або PNG",
                too_big=f"Фото «{{name}}» більше за {settings.max_review_photo_mb} МБ"))
        db.add_all(ReviewPhoto(review_id=review.id, file_path=path) for path in saved)
        db.flush()
    except BaseException:
        for path in saved:
            private_files.remove(path)
        raise
    return saved


# ---------- the client writes a review
def _was_completed(db: Session, order: Order) -> bool:
    return db.scalar(select(func.count()).where(
        OrderStatusHistory.order_id == order.id,
        OrderStatusHistory.new_status == OrderStatus.COMPLETED.value)) > 0


def create_review(db: Session, client: User, order: Order, data: dict[str, Any],
                  photos: list[FileUpload]) -> Review:
    """Form 4.6.1.4, field 1: only for a trip that took place — «Завершено», or «Архівний» after
    «Завершено» (an archived rejected / cancelled order had no trip)."""
    from app.services.payments.service import lock_order

    order = lock_order(db, order.id)          # two clicks cannot create two reviews
    if not (order.status == OrderStatus.COMPLETED
            or (order.status == OrderStatus.ARCHIVED and _was_completed(db, order))):
        raise DomainError("Відгук можна залишити лише після завершення подорожі", 409)
    if db.scalar(select(Review.id).where(Review.order_id == order.id)) is not None:
        raise DomainError("Відгук до цього замовлення вже залишено", 409)
    review = Review(order_id=order.id, tour_id=order.tour_id, hotel_id=order.tour.hotel_id,
                    user_id=client.id, status=ReviewStatus.PENDING, submitted_at=utcnow(),
                    name_display=data.get("name_display") or NameDisplay.SHORT)
    _apply(review, {k: v for k, v in data.items() if k != "name_display"} | {
        "hotel_rating": data.get("hotel_rating"), "service_rating": data.get("service_rating")})
    saved: list[str] = []
    try:
        with db.begin_nested():
            db.add(review)
            db.flush()
            saved = _save_photos(db, review, photos)
            if not review_premoderation(db):
                publish(db, review, None)
    except IntegrityError:                    # the unique order_id won a race
        _remove(saved)
        raise DomainError("Відгук до цього замовлення вже залишено", 409) from None
    except BaseException:
        _remove(saved)
        raise
    db.refresh(review, ["photos"])
    return review


def _remove(paths: list[str]) -> None:
    for path in paths:
        private_files.remove(path)


def list_own(db: Session, client: User, page: int, page_size: int) -> tuple[list[Review], int]:
    query = select(Review).where(Review.user_id == client.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Review.created_at.desc(), Review.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_own(db: Session, client: User, review_id: int, lock: bool = False) -> Review:
    query = select(Review).where(Review.id == review_id, Review.user_id == client.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    review = db.scalar(query)
    if review is None:
        raise DomainError("Відгук не знайдено", 404)
    return review


def resubmit(db: Session, client: User, review_id: int, data: dict[str, Any],
             photos: list[FileUpload] | None, clear_photos: bool) -> tuple[Review, list[str]]:
    """A rejected review may be corrected and sent to moderation again — once. New photos, if
    sent, replace all old ones. Returns the old photo files to delete after the commit."""
    review = get_own(db, client, review_id, lock=True)
    if review.status != ReviewStatus.REJECTED:
        raise DomainError(f"Виправити можна лише відхилений відгук; цей — "
                          f"{STATUS_LABELS[review.status]}", 409)
    if review.resubmitted_at is not None:
        raise DomainError("Відгук уже виправлявся один раз — повторне подання неможливе", 409)
    old_paths: list[str] = []
    saved: list[str] = []
    try:
        with db.begin_nested():
            _apply(review, data)
            if photos or clear_photos:
                old_paths = [p.file_path for p in review.photos]
                for photo in list(review.photos):
                    db.delete(photo)
                db.flush()
                saved = _save_photos(db, review, photos or [])
            now = utcnow()
            review.status, review.reject_reason = ReviewStatus.PENDING, None
            review.moderated_by, review.moderated_at = None, None
            review.submitted_at, review.resubmitted_at = now, now
            db.flush()
            if not review_premoderation(db):
                publish(db, review, None)
    except BaseException:
        _remove(saved)
        raise
    db.refresh(review, ["photos"])
    return review, old_paths


# ---------- moderation and the hotel rating
def recalc_hotel_rating(db: Session, hotel_id: int) -> Decimal | None:
    """hotels.rating_avg = average hotel_rating of the hotel's published reviews, 2 places
    (ROUND_HALF_UP, like PostgreSQL ROUND on numeric); NULL when there are none. The hotel row is
    locked so two moderators publishing at once cannot overwrite each other's result."""
    hotel = db.scalar(select(Hotel).where(Hotel.id == hotel_id).with_for_update()
                      .execution_options(populate_existing=True))
    average = db.scalar(select(func.avg(Review.hotel_rating))
                        .where(Review.hotel_id == hotel_id, Review.status == ReviewStatus.PUBLISHED))
    hotel.rating_avg = (Decimal(average).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        if average is not None else None)
    db.flush()
    return hotel.rating_avg


def publish(db: Session, review: Review, moderator: User | None) -> Review:
    review.status, review.reject_reason = ReviewStatus.PUBLISHED, None
    review.moderated_by, review.moderated_at = (moderator.id if moderator else None), utcnow()
    db.flush()
    recalc_hotel_rating(db, review.hotel_id)
    return review


# ---------- photos: published = public; otherwise only the author and managers
def photo_file(db: Session, review_id: int, photo_id: int, viewer: User | None) -> tuple[str, str, bool]:
    """(absolute path, media type, is public). Anything not visible to `viewer` is 404, so a
    guest cannot even learn that an unpublished review exists."""
    from app.models.enums import UserRole

    photo = db.get(ReviewPhoto, photo_id)
    review = photo.review if photo is not None else None
    if review is None or review.id != review_id:
        raise DomainError("Фото не знайдено", 404)
    public = review.status == ReviewStatus.PUBLISHED
    allowed = public or (viewer is not None and (viewer.id == review.user_id
                                                 or viewer.role == UserRole.MANAGER))
    if not allowed:
        raise DomainError("Фото не знайдено", 404)
    path = private_files.absolute(photo.file_path)
    if not path.exists():
        raise DomainError("Фото не знайдено", 404)
    return str(path), private_files.media_type(photo.file_path)[1], public


# ---------- the moderator (role manager)
def list_for_moderation(db: Session, *, status: ReviewStatus, tour_id: int | None,
                        hotel_id: int | None, page: int, page_size: int) -> tuple[list[Review], int]:
    """The queue: oldest submitted first (a resubmitted review queues again by its new time)."""
    query = select(Review).where(Review.status == status)
    if tour_id is not None:
        query = query.where(Review.tour_id == tour_id)
    if hotel_id is not None:
        query = query.where(Review.hotel_id == hotel_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Review.submitted_at, Review.id)
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_review(db: Session, review_id: int, lock: bool = False) -> Review:
    query = select(Review).where(Review.id == review_id)
    if lock:                                  # review row first, then the hotel row
        query = query.with_for_update().execution_options(populate_existing=True)
    review = db.scalar(query)
    if review is None:
        raise DomainError("Відгук не знайдено", 404)
    return review


def moderate_publish(db: Session, moderator: User, review_id: int) -> Review:
    from app.services.notifications import notify

    review = get_review(db, review_id, lock=True)
    if review.status != ReviewStatus.PENDING:
        raise DomainError(f"Опублікувати можна лише відгук на модерації; цей — "
                          f"{STATUS_LABELS[review.status]}", 409)
    publish(db, review, moderator)
    notify(db, review.user_id, "Ваш відгук опубліковано",
           f"Дякуємо! Відгук про тур «{review.tour.title_uk}» тепер бачать усі відвідувачі сайту.",
           review.order)
    return review


def moderate_reject(db: Session, moderator: User, review_id: int, reason: str) -> Review:
    """Pending -> rejected, or published -> rejected (unpublish: the hotel rating is recalculated)."""
    from app.services.notifications import notify

    review = get_review(db, review_id, lock=True)
    if review.status == ReviewStatus.REJECTED:
        raise DomainError("Відгук уже відхилено", 409)
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Вкажіть причину відхилення", 422)
    if len(reason) > MAX_REASON:
        raise DomainError(f"Причина — не довше {MAX_REASON} символів", 422)
    was_published = review.status == ReviewStatus.PUBLISHED
    review.status, review.reject_reason = ReviewStatus.REJECTED, reason
    review.moderated_by, review.moderated_at = moderator.id, utcnow()
    db.flush()
    if was_published:
        recalc_hotel_rating(db, review.hotel_id)
    hint = (" Ви можете один раз виправити відгук у розділі «Мої відгуки» і подати його знову."
            if can_resubmit(review) else "")
    notify(db, review.user_id, "Відгук не опубліковано" if not was_published else "Відгук знято з публікації",
           f"Відгук про тур «{review.tour.title_uk}»: {reason}.{hint}", review.order)
    return review


# ---------- public: published reviews only
def public_reviews(db: Session, *, tour_id: int | None = None, hotel_id: int | None = None,
                   page: int, page_size: int) -> tuple[list[Review], int]:
    """Newest published first. 404 for a tour that is not public at all (a draft) or a hotel that
    does not exist; reviews of archived tours stay visible (the trip took place)."""
    from app.models import Tour
    from app.models.enums import TourStatus

    query = select(Review).where(Review.status == ReviewStatus.PUBLISHED)
    if tour_id is not None:
        tour = db.get(Tour, tour_id)
        if tour is None or tour.status == TourStatus.DRAFT:
            raise DomainError("Тур не знайдено", 404)
        query = query.where(Review.tour_id == tour_id)
    if hotel_id is not None:
        if db.get(Hotel, hotel_id) is None:
            raise DomainError("Готель не знайдено", 404)
        query = query.where(Review.hotel_id == hotel_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Review.moderated_at.desc().nulls_last(), Review.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def tour_review_stats(db: Session, tour_id: int) -> tuple[int, Decimal | None]:
    """(published reviews of the tour, average service rating, 2 places) for the tour page."""
    count, average = db.execute(select(func.count(), func.avg(Review.service_rating))
                                .where(Review.tour_id == tour_id,
                                       Review.status == ReviewStatus.PUBLISHED)).one()
    return count, (Decimal(average).quantize(Decimal("0.01"), ROUND_HALF_UP)
                   if average is not None else None)
