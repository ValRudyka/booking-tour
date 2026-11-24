"""Payments, refunds, reviews and the audit log."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.enums import Currency, NameDisplay, PaymentMethod, PaymentType, TransactionStatus


class Payment(TimestampMixin, Base):
    """One row per money movement: a payment or a refund (ТЗ form 4.6.3.1)."""
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_uah > 0", name="amount_positive"),
        CheckConstraint("type = 'refund' OR refund_of_id IS NULL", name="refund_of_only_refunds"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    type: Mapped[PaymentType] = mapped_column(str_enum(PaymentType, "payment_type"))
    # A refund row points at the payment it returns money from: with several payments per order
    # (partial bank transfers + card) this tells how much of each payment is still refundable.
    refund_of_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), index=True)
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "payment_method"))
    status: Mapped[TransactionStatus] = mapped_column(
        str_enum(TransactionStatus, "transaction_status"),
        default=TransactionStatus.PENDING, server_default=TransactionStatus.PENDING.value)
    amount_uah: Mapped[Decimal]                       # expected amount («Очікувана сума»)
    paid_amount: Mapped[Decimal | None]               # actually received («Фактично сплачено»)
    currency: Mapped[Currency] = mapped_column(str_enum(Currency, "currency"),
                                               default=Currency.UAH, server_default="UAH")
    purpose: Mapped[str | None] = mapped_column(String(300))  # bank statement text
    received_at: Mapped[datetime | None]
    bank_statement_path: Mapped[str | None] = mapped_column(String(300))
    controller_comment: Mapped[str | None] = mapped_column(Text)
    # Stripe identifiers (test mode)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(255))
    stripe_refund_id: Mapped[str | None] = mapped_column(String(255), unique=True)  # webhook lookup
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    order: Mapped["Order"] = relationship(back_populates="payments")


class Review(TimestampMixin, Base):
    """One review per completed order (ТЗ form 4.6.1.4)."""
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("hotel_rating BETWEEN 1 AND 5", name="hotel_rating_range"),
        CheckConstraint("service_rating BETWEEN 1 AND 5", name="service_rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    hotel_rating: Mapped[int] = mapped_column(SmallInteger)
    service_rating: Mapped[int] = mapped_column(SmallInteger)
    positive: Mapped[str | None] = mapped_column(Text)
    negative: Mapped[str | None] = mapped_column(Text)
    name_display: Mapped[NameDisplay] = mapped_column(str_enum(NameDisplay, "name_display"),
                                                      default=NameDisplay.SHORT,
                                                      server_default=NameDisplay.SHORT.value)
    is_published: Mapped[bool] = mapped_column(default=False, server_default="false")  # moderation

    photos: Mapped[list["ReviewPhoto"]] = relationship(back_populates="review",
                                                       cascade="all, delete-orphan")


class ReviewPhoto(Base):
    __tablename__ = "review_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(300))

    review: Mapped[Review] = relationship(back_populates="photos")


class AuditLog(TimestampMixin, Base):
    """Who changed what (ТЗ 5.9, 7). user_id = NULL means the System."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
