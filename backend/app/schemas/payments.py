"""Payment schemas: the client's «Оплатити», the return page, the finance register (form 4.6.3.1)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (CancelReason, Currency, OrderStatus, PaymentMethod, PaymentStatus,
                              PaymentType, TransactionStatus)


class PayRequest(BaseModel):
    method: PaymentMethod = PaymentMethod.CARD


class BankDetailsOut(BaseModel):
    recipient: str
    iban: str
    edrpou: str
    bank_name: str
    amount_uah: Decimal
    purpose: str
    pay_until: datetime | None


class PaymentShortOut(BaseModel):
    """A money movement of the order, as the client sees it."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: PaymentType
    method: PaymentMethod
    status: TransactionStatus
    amount_uah: Decimal
    paid_amount: Decimal | None
    received_at: datetime | None
    created_at: datetime


class PayOut(BaseModel):
    order_id: int
    order_number: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    payment: PaymentShortOut | None
    checkout_url: str | None = None        # card: redirect the client here
    bank_details: BankDetailsOut | None = None
    message: str | None = None


class PaymentResultOut(BaseModel):
    """Where Stripe sends the client back (until the frontend exists)."""
    order_number: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    payment: TransactionStatus
    message: str


class FinancePaymentOut(BaseModel):
    """One row of the register «Фінанси / Транзакції» (form 4.6.3.1)."""
    id: int                                 # field 1 «ID Транзакції»
    order_id: int                           # field 2 «ID Заявки»
    order_number: str
    order_status: OrderStatus
    order_payment_status: PaymentStatus     # field 6 «Фінансовий статус»
    type: PaymentType
    method: PaymentMethod
    status: TransactionStatus
    amount_uah: Decimal                     # field 3 «Очікувана сума»
    paid_amount: Decimal | None             # field 4 «Фактично сплачено»
    currency: Currency                      # field 5
    purpose: str | None                     # field 7
    received_at: datetime | None            # field 8
    has_statement: bool                     # field 10
    controller_comment: str | None          # field 11
    confirmed_by: int | None
    stripe_session_id: str | None
    stripe_payment_intent: str | None
    stripe_refund_id: str | None
    created_at: datetime


class RefundQueueItem(BaseModel):
    """A row of the finance queue «Повернення» (scenario 4.5.6)."""
    order_id: int
    order_number: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    # cancel_request | rejected | refund_failed (money back with us) | refund_pending (Stripe) |
    # unfinished_transfer (partly paid by transfer, the rest never came)
    kind: str
    client_name: str
    total_uah: Decimal
    paid_uah: Decimal                       # succeeded payments
    refunded_uah: Decimal                   # succeeded refunds
    pending_refund_uah: Decimal
    kept_uah: Decimal                       # still with the company
    fpv_uah: Decimal | None                 # ФПВ already decided (after a first refund attempt)
    cancel_reason_code: CancelReason | None
    cancel_reason: str | None
    reject_reason: str | None
    created_at: datetime


class RefundRowOut(BaseModel):
    """One refund row this request created."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    refund_of_id: int | None                # the payment the money is returned from
    method: PaymentMethod
    status: TransactionStatus
    amount_uah: Decimal
    stripe_refund_id: str | None


class RefundOut(BaseModel):
    order_id: int
    order_number: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    fpv_uah: Decimal | None
    refunded_now_uah: Decimal
    rows: list[RefundRowOut]
    finished: bool                          # False: a Stripe refund is pending (webhook finishes it)
    message: str
