"""Order views shared by the staff routers (manager and finance see the same order card)."""
from app.models import Order
from app.schemas.manager_orders import ManagerOrderDetailOut, PersonOut
from app.services.order_processing import short_name


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
