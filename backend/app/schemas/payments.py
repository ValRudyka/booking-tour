"""Payment schemas: the client's «Оплатити», the return page, the finance register (form 4.6.3.1)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (Currency, OrderStatus, PaymentMethod, PaymentStatus, PaymentType,
                              TransactionStatus)


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
