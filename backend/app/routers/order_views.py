"""Views shared by several routers: the staff order card (manager and finance) and reviews."""
from app.models import Order, Review
from app.schemas.manager_orders import ManagerOrderDetailOut, PersonOut
from app.schemas.reviews import MyReviewOut, PublicReviewOut, ReviewPhotoOut, StaffReviewOut
from app.services.order_processing import short_name
from app.services.reviews import author_name, can_resubmit


def order_row(order: Order) -> dict:
    client = order.client
    return dict(id=order.id, number=order.number, status=order.status,
                payment_status=order.payment_status, tour_id=order.tour_id,
                tour_title_uk=order.tour.title_uk, hotel_name=order.tour.hotel.name,
                start_date=order.start_date, end_date=order.end_date, adults=order.adults,
                children=order.children, total_uah=order.total_uah,
                client_name=f"{client.last_name} {client.first_name}", manager_id=order.manager_id,
                manager_name=short_name(order.manager), pnr=order.pnr,
                created_at=order.created_at)


def staff_detail(order: Order) -> ManagerOrderDetailOut:
    client = order.client
    return ManagerOrderDetailOut(
        **order_row(order),
        client=PersonOut(id=client.id, last_name=client.last_name, first_name=client.first_name,
                         phone=client.phone, email=client.email),
        wishes=order.wishes, insurance_type_id=order.insurance_type_id,
        transfer_type_id=order.transfer_type_id,
        promo_code=order.promo.code if order.promo else None, discount_uah=order.discount_uah,
        operator_deadline=order.operator_deadline, internal_comment=order.internal_comment,
        reject_reason=order.reject_reason, cancel_reason_code=order.cancel_reason_code,
        cancel_reason=order.cancel_reason, fpv_uah=order.fpv_uah, tourists=order.tourists,
        payments=order.payments, documents=sorted(order.documents, key=lambda d: d.id),
        history=order.history)


# ---------- reviews
def _content(review: Review) -> dict:
    return dict(hotel_rating=review.hotel_rating, service_rating=review.service_rating,
                positive=review.positive, negative=review.negative,
                photos=[ReviewPhotoOut(id=p.id, url=f"/api/reviews/{review.id}/photos/{p.id}")
                        for p in review.photos])


def public_review(review: Review) -> PublicReviewOut:
    return PublicReviewOut(**_content(review), id=review.id, author=author_name(review),
                           tour_id=review.tour_id, tour_title_uk=review.tour.title_uk,
                           hotel_name=review.hotel.name,
                           trip_month=review.order.start_date.strftime("%Y-%m"),
                           published_at=review.moderated_at)


def my_review(review: Review) -> MyReviewOut:
    return MyReviewOut(**_content(review), id=review.id, order_id=review.order_id,
                       tour_id=review.tour_id, tour_title_uk=review.tour.title_uk,
                       hotel_name=review.hotel.name, name_display=review.name_display,
                       author=author_name(review), status=review.status,
                       reject_reason=review.reject_reason, can_resubmit=can_resubmit(review),
                       submitted_at=review.submitted_at, moderated_at=review.moderated_at,
                       created_at=review.created_at)


def staff_review(review: Review) -> StaffReviewOut:
    user = review.author
    return StaffReviewOut(**my_review(review).model_dump(), order_number=review.order.number,
                          hotel_id=review.hotel_id, user_id=review.user_id,
                          author_full_name=f"{user.last_name} {user.first_name}",
                          moderated_by=review.moderated_by, resubmitted_at=review.resubmitted_at)
