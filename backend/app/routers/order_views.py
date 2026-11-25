"""Views shared by several routers: the staff order card (manager and finance) and reviews."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Review, User
from app.schemas.manager_orders import (ManagerOrderDetailOut, PersonOut, StaffHistoryOut,
                                        StaffOrderDocumentOut)
from app.schemas.reviews import MyReviewOut, PublicReviewOut, ReviewPhotoOut, StaffReviewOut
from app.services.order_processing import is_overdue, short_name
from app.services.staff_actions import document_can_delete, staff_actions
from app.services.reviews import author_name, can_resubmit


def order_row(order: Order) -> dict:
    client = order.client
    return dict(id=order.id, number=order.number, status=order.status,
                payment_status=order.payment_status, tour_id=order.tour_id,
                tour_title_uk=order.tour.title_uk, hotel_name=order.tour.hotel.name,
                start_date=order.start_date, end_date=order.end_date, adults=order.adults,
                children=order.children, total_uah=order.total_uah,
                client_name=f"{client.last_name} {client.first_name}", client_phone=client.phone,
                manager_id=order.manager_id, manager_name=short_name(order.manager), pnr=order.pnr,
                overdue=is_overdue(order), created_at=order.created_at)


def _history(db: Session, order: Order) -> list[StaffHistoryOut]:
    ids = {h.changed_by for h in order.history if h.changed_by is not None}
    names = {u.id: short_name(u) for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    return [StaffHistoryOut(old_status=h.old_status, new_status=h.new_status, changed_by=h.changed_by,
                            changed_by_name=names.get(h.changed_by), comment=h.comment,
                            changed_at=h.changed_at) for h in order.history]


def staff_detail(db: Session, order: Order, viewer: User) -> ManagerOrderDetailOut:
    """The staff order card. Actions and document deletion are worked out for `viewer`."""
    client = order.client
    tour = order.tour
    resort = tour.hotel.resort
    documents = [StaffOrderDocumentOut(id=d.id, doc_type=d.doc_type, uploaded_at=d.uploaded_at,
                                       uploaded_by=d.uploaded_by,
                                       can_delete=document_can_delete(order, viewer, d))
                 for d in sorted(order.documents, key=lambda d: d.id)]
    return ManagerOrderDetailOut(
        **order_row(order),
        client=PersonOut(id=client.id, last_name=client.last_name, first_name=client.first_name,
                         phone=client.phone, email=client.email),
        wishes=order.wishes, insurance_type_id=order.insurance_type_id,
        insurance_name=order.insurance_type.name_uk if order.insurance_type else None,
        transfer_type_id=order.transfer_type_id,
        transfer_name=order.transfer_type.name_uk if order.transfer_type else None,
        country_name=resort.country.name_uk, resort_name=resort.name_uk,
        departure_city_name=tour.departure_city.name_uk if tour.departure_city else None,
        transport_type=tour.transport_type, meal_plan=tour.meal_plan,
        promo_code=order.promo.code if order.promo else None, discount_uah=order.discount_uah,
        operator_deadline=order.operator_deadline, internal_comment=order.internal_comment,
        reject_reason=order.reject_reason, cancel_reason_code=order.cancel_reason_code,
        cancel_reason=order.cancel_reason, fpv_uah=order.fpv_uah, tourists=order.tourists,
        payments=order.payments, documents=documents, history=_history(db, order),
        staff_actions=staff_actions(db, order, viewer))


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
