"""Reference data (довідники) and global settings — managed by the system administrator."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, String, Text, func,
                        text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum
from app.models.enums import Currency


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_code: Mapped[str] = mapped_column(String(2), unique=True)
    name_uk: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100))
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")

    resorts: Mapped[list["Resort"]] = relationship(back_populates="country")


class City(Base):
    """Departure cities / airports (ТЗ form 4.6.2.1, field 7)."""
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    name_uk: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100))
    iata_code: Mapped[str | None] = mapped_column(String(3))
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")


class Resort(Base):
    __tablename__ = "resorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    name_uk: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100))
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")

    country: Mapped[Country] = relationship(back_populates="resorts")
    hotels: Mapped[list["Hotel"]] = relationship(back_populates="resort")


class Hotel(Base):
    __tablename__ = "hotels"
    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5", name="stars_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resort_id: Mapped[int] = mapped_column(ForeignKey("resorts.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    stars: Mapped[int | None] = mapped_column(SmallInteger)
    description: Mapped[str | None] = mapped_column(Text)
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))  # recalculated from reviews
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")

    resort: Mapped[Resort] = relationship(back_populates="hotels")


class InsuranceType(Base):
    """Довідник «Страхування»: Базове / Розширене / Без франшизи."""
    __tablename__ = "insurance_types"
    # At most one default in the database itself; the service keeps exactly one.
    __table_args__ = (Index("uq_insurance_types_single_default", "is_default", unique=True,
                            postgresql_where=text("is_default")),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name_uk: Mapped[str] = mapped_column(String(100))
    price_uah: Mapped[Decimal]  # per tourist
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")


class TransferType(Base):
    """Довідник «Трансфер»: Груповий / Індивідуальний / VIP."""
    __tablename__ = "transfer_types"
    # At most one default in the database itself; the service keeps exactly one.
    __table_args__ = (Index("uq_transfer_types_single_default", "is_default", unique=True,
                            postgresql_where=text("is_default")),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name_uk: Mapped[str] = mapped_column(String(100))
    price_uah: Mapped[Decimal]  # per order
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")


class CurrencyRate(Base):
    """Commercial exchange rates set by the admin (ТЗ form 4.6.4.1, fields 1-2)."""
    __tablename__ = "currency_rates"
    __table_args__ = (CheckConstraint("rate_to_uah > 0", name="rate_positive"),)

    currency: Mapped[Currency] = mapped_column(str_enum(Currency, "currency"), primary_key=True)
    rate_to_uah: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Language(Base):
    """Available interface languages (ТЗ form 4.6.4.1, field 5)."""
    __tablename__ = "languages"

    code: Mapped[str] = mapped_column(String(5), primary_key=True)  # "uk", "en"
    name: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(default=True, server_default="true")


class Setting(Base):
    """Key-value global settings: acquiring_percent, booking_timeout_min,
    system_email, maintenance_mode (ТЗ form 4.6.4.1)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
