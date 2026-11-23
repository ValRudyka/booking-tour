"""Orders and everything attached to them (ТЗ 4.4.1, forms 4.6.1.2, 4.6.2.2, 4.6.2.3)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, ForeignKey, Numeric, Sequence, SmallInteger, String, Text,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.catalog import Tour
from app.models.enums import DiscountType, OrderDocumentType, OrderStatus, PaymentStatus

# Source of order numbers TU-<year>-<nnnnnn>. A sequence hands out each value exactly once even
# under concurrent checkouts (MAX()+1 would race), and the number is known before the INSERT.
# Created by migration 'order number sequence'; Alembic autogenerate does not compare sequences.
ORDER_NUMBER_SEQ = Sequence("order_number_seq", metadata=Base.metadata)


class PromoCode(TimestampMixin, Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("discount_value > 0", name="discount_positive"),
        CheckConstraint("discount_type = 'fixed' OR discount_value <= 100", name="percent_max_100"),
        CheckConstraint("valid_to >= valid_from", name="validity_order"),
        CheckConstraint("usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType, "discount_type"))
    discount_value: Mapped[Decimal]
    min_order_uah: Mapped[Decimal | None]
    valid_from: Mapped[date]
    valid_to: Mapped[date]
    usage_limit: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("adults >= 1", name="at_least_one_adult"),
        CheckConstraint("children >= 0", name="children_non_negative"),
        CheckConstraint("end_date > start_date", name="dates_order"),
        CheckConstraint("total_uah >= 0", name="total_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. TU-2026-000123
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, "order_status"),
                                                default=OrderStatus.CHECKOUT,
                                                server_default=OrderStatus.CHECKOUT.value, index=True)
    payment_status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus, "payment_status"),
                                                          default=PaymentStatus.AWAITING,
                                                          server_default=PaymentStatus.AWAITING.value)
    start_date: Mapped[date]
    end_date: Mapped[date]                 # start_date + tour.nights; «Завершено» the day after
    adults: Mapped[int] = mapped_column(SmallInteger)
    children: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    insurance_type_id: Mapped[int | None] = mapped_column(ForeignKey("insurance_types.id"))
    transfer_type_id: Mapped[int | None] = mapped_column(ForeignKey("transfer_types.id"))
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"))
    wishes: Mapped[str | None] = mapped_column(Text)
    # Price is frozen at checkout: later rate changes must not change a placed order.
    total_uah: Mapped[Decimal]
    discount_uah: Mapped[Decimal] = mapped_column(default=0, server_default="0")
    rate_used: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    hold_expires_at: Mapped[datetime | None]  # seat hold during checkout / awaiting payment
    # When the client accepted the public offer (form 4.6.1.2, field 9) — set by «Перейти до оплати».
    offer_accepted_at: Mapped[datetime | None]
    # Manager's technical analysis (form 4.6.2.2)
    pnr: Mapped[str | None] = mapped_column(String(20))
    operator_deadline: Mapped[date | None]
    internal_comment: Mapped[str | None] = mapped_column(Text)  # managers only
    reject_reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    tour: Mapped[Tour] = relationship()
    tourists: Mapped[list["OrderTourist"]] = relationship(back_populates="order",
                                                          cascade="all, delete-orphan")
    documents: Mapped[list["OrderDocument"]] = relationship(back_populates="order",
                                                            cascade="all, delete-orphan")
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.changed_at")


class OrderTourist(Base):
    """Copy of passport data for this order (not a link to saved_passports on purpose)."""
    __tablename__ = "order_tourists"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    last_name_lat: Mapped[str] = mapped_column(String(100))
    first_name_lat: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date]                 # adult / child (under 12) for pricing
    passport_number: Mapped[str] = mapped_column(String(20))
    passport_expiry: Mapped[date]

    order: Mapped[Order] = relationship(back_populates="tourists")


class OrderDocument(Base):
    __tablename__ = "order_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[OrderDocumentType] = mapped_column(
        str_enum(OrderDocumentType, "order_document_type"))
    file_path: Mapped[str] = mapped_column(String(300))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="documents")


class OrderStatusHistory(Base):
    """Every status change. changed_by = NULL means the System did it (timeout, auto-complete)."""
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="history")
