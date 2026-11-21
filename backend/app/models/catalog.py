"""Tour catalog: tours, day-by-day program, photo gallery (ТЗ form 4.6.2.1)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.enums import Currency, TourStatus, TransportType
from app.models.reference import City, Hotel


class Tour(TimestampMixin, Base):
    __tablename__ = "tours"
    __table_args__ = (
        CheckConstraint("nights BETWEEN 1 AND 30", name="nights_range"),
        CheckConstraint("departure_to >= departure_from", name="departure_dates_order"),
        CheckConstraint("base_price > 0", name="base_price_positive"),
        CheckConstraint("child_price IS NULL OR child_price >= 0", name="child_price_non_negative"),
        CheckConstraint("seats_sold >= 0 AND seats_sold <= seats_total", name="seats_within_quota"),
        CheckConstraint("transport_type = 'none' OR departure_city_id IS NOT NULL",
                        name="departure_city_required"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_uk: Mapped[str] = mapped_column(String(200))
    title_en: Mapped[str] = mapped_column(String(200))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), index=True)
    # Transport and logistics
    transport_type: Mapped[TransportType] = mapped_column(str_enum(TransportType, "transport_type"))
    departure_city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    flight_out: Mapped[str | None] = mapped_column(String(10))
    flight_back: Mapped[str | None] = mapped_column(String(10))
    # Commercial terms and quota. A tour can be booked for any start date in the range.
    departure_from: Mapped[date] = mapped_column(index=True)
    departure_to: Mapped[date]
    nights: Mapped[int] = mapped_column(SmallInteger)
    seats_total: Mapped[int]                                          # «Жорсткий блок місць»
    seats_sold: Mapped[int] = mapped_column(default=0, server_default="0")  # written off after payment
    base_price: Mapped[Decimal]                                       # per adult, in tour currency
    child_price: Mapped[Decimal | None]                               # NULL = same as base_price
    currency: Mapped[Currency] = mapped_column(str_enum(Currency, "currency"))
    # Content and publication
    description: Mapped[str | None] = mapped_column(Text)
    is_featured: Mapped[bool] = mapped_column(default=False, server_default="false")
    status: Mapped[TourStatus] = mapped_column(str_enum(TourStatus, "tour_status"),
                                               default=TourStatus.DRAFT,
                                               server_default=TourStatus.DRAFT.value, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    hotel: Mapped[Hotel] = relationship()
    departure_city: Mapped[City | None] = relationship()
    program_days: Mapped[list["TourProgramDay"]] = relationship(
        back_populates="tour", cascade="all, delete-orphan", order_by="TourProgramDay.day_number")
    images: Mapped[list["TourImage"]] = relationship(
        back_populates="tour", cascade="all, delete-orphan", order_by="TourImage.sort_order")


class TourProgramDay(Base):
    __tablename__ = "tour_program_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), index=True)
    day_number: Mapped[int] = mapped_column(SmallInteger)
    description: Mapped[str] = mapped_column(Text)

    tour: Mapped[Tour] = relationship(back_populates="program_days")


class TourImage(Base):
    __tablename__ = "tour_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    tour: Mapped[Tour] = relationship(back_populates="images")
