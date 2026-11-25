"""Manager's order processing (form 4.6.2.2) and order documents."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (CancelReason, MealPlan, OrderDocumentType, OrderStatus, PaymentStatus,
                              StaffAction, TransportType)
from app.schemas.common import Page
from app.schemas.orders import StatusHistoryOut, TouristOut
from app.schemas.payments import PaymentShortOut


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: OrderDocumentType
    uploaded_at: datetime


class StaffDocumentOut(DocumentOut):
    uploaded_by: int


class StaffOrderDocumentOut(StaffDocumentOut):
    can_delete: bool                     # the delete endpoint would accept it from this user


class StaffHistoryOut(StatusHistoryOut):
    changed_by_name: str | None          # NULL with changed_by NULL = the System


class StaffActionOut(BaseModel):
    """One action of services/staff_actions.py: allowed, or refused with the server's reason
    (shown next to a disabled button)."""
    action: StaffAction
    allowed: bool
    reason: str | None


class StaffPaymentOut(PaymentShortOut):
    refund_of_id: int | None
    stripe_refund_id: str | None
    controller_comment: str | None


class PersonOut(BaseModel):
    id: int
    last_name: str
    first_name: str
    phone: str
    email: str


class ManagerOrderOut(BaseModel):
    """A row of «Вхідні заявки»."""
    id: int
    number: str                          # field 1 «ID Заявки»
    status: OrderStatus                  # field 2 «Робочий статус»
    payment_status: PaymentStatus
    tour_id: int
    tour_title_uk: str
    hotel_name: str
    start_date: date
    end_date: date
    adults: int
    children: int
    total_uah: Decimal
    client_name: str
    client_phone: str
    manager_id: int | None               # field 8 «Відповідальний»
    manager_name: str | None
    pnr: str | None
    overdue: bool                        # the trip date came, documents never got ready
    created_at: datetime


class QueueCountsOut(BaseModel):
    new: int
    mine: int
    all: int


class ManagerOrderPage(Page[ManagerOrderOut]):
    queue_counts: QueueCountsOut         # tabs «Нові / Мої / Усі», independent of the filters


class ManagerShortOut(BaseModel):
    id: int
    name: str


class DocumentRulesOut(BaseModel):
    """The manager's upload form: trip document types and file limits (the server checks again,
    including the file contents)."""
    doc_types: list[OrderDocumentType]
    max_documents: int                   # per order, the client's cancellation files included
    max_file_mb: int
    file_types: list[str]                # extensions: "pdf", "jpg", "png"


class ManagerOrderDetailOut(ManagerOrderOut):
    client: PersonOut
    wishes: str | None
    insurance_type_id: int | None
    insurance_name: str | None
    transfer_type_id: int | None
    transfer_name: str | None
    country_name: str
    resort_name: str
    departure_city_name: str | None
    transport_type: TransportType
    meal_plan: MealPlan | None
    promo_code: str | None
    discount_uah: Decimal
    operator_deadline: date | None       # field 4
    internal_comment: str | None         # field 6, managers only
    reject_reason: str | None
    cancel_reason_code: CancelReason | None
    cancel_reason: str | None
    fpv_uah: Decimal | None
    tourists: list[TouristOut]           # passport data: staff and the order's own client only
    payments: list[StaffPaymentOut]
    documents: list[StaffOrderDocumentOut]   # field 5, plus the client's cancellation evidence
    history: list[StaffHistoryOut]
    staff_actions: list[StaffActionOut]  # for the viewer; empty for roles other than manager


class ClientMessage(BaseModel):
    client_message: str | None = Field(None, description="Повідомлення клієнту (поле 7)")


class ConfirmIn(ClientMessage):
    pnr: str = Field(max_length=40, description="GDS номер (PNR)")
    operator_deadline: date = Field(description="Дедлайн оплати туроператору")


class RejectIn(ClientMessage):
    reject_reason: str = Field(max_length=4000)


class AssignIn(BaseModel):
    manager_id: int


class ManagerOrderPatch(BaseModel):
    """Only the internal comment is edited here; everything else has its own action."""
    model_config = ConfigDict(extra="forbid")

    internal_comment: str | None
