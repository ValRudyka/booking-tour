"""Users, their saved passports and personal-account features."""
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.enums import UserRole


class User(TimestampMixin, Base):
    """All people in the system; `role` decides what they may do (ТЗ 4.3)."""
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("loyalty_points >= 0", name="loyalty_points_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)    # login (form 4.6.1.1, field 1)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"), default=UserRole.CLIENT,
                                           server_default=UserRole.CLIENT.value, index=True)
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date | None]
    citizenship_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"))
    consent_at: Mapped[datetime | None]  # personal-data consent (form 4.6.1.1, field 9)
    loyalty_points: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Tokens issued before this moment (JWT iat, whole seconds) are rejected: set when the admin
    # resets the password. Stored truncated to whole seconds, like iat (see core/deps.py).
    tokens_valid_after: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    passports: Mapped[list["SavedPassport"]] = relationship(back_populates="user",
                                                            cascade="all, delete-orphan")


class SavedPassport(Base):
    """Foreign passports saved for quick checkout autofill (form 4.6.1.1, field 8)."""
    __tablename__ = "saved_passports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_name_lat: Mapped[str] = mapped_column(String(100))
    first_name_lat: Mapped[str] = mapped_column(String(100))
    passport_number: Mapped[str] = mapped_column(String(20))
    issuing_authority: Mapped[str | None] = mapped_column(String(4))  # 4-digit code
    expiry_date: Mapped[date]
    # For the full checkout autofill (form 4.6.1.2, field 3.6). Required by the API; NULL only in
    # rows saved before it existed (the checkout then asks for it).
    birth_date: Mapped[date | None]

    user: Mapped[User] = relationship(back_populates="passports")


class Notification(TimestampMixin, Base):
    """In-app notifications shown in the personal account (and optionally e-mailed)."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(default=False, server_default="false")


class Favorite(TimestampMixin, Base):
    """«Обране» (extra feature, ТЗ 5.7)."""
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), primary_key=True)


class SearchHistory(TimestampMixin, Base):
    """«Історія пошуку» (extra feature, ТЗ 5.7). `params` = the filters used."""
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)


class LoyaltyTransaction(TimestampMixin, Base):
    """Loyalty points accrual (+) / spending (-) (extra feature, ТЗ 5.7)."""
    __tablename__ = "loyalty_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    points: Mapped[int]
    reason: Mapped[str] = mapped_column(String(200))
