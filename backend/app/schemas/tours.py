"""Tour schemas: the manager's form 4.6.2.1 and the public catalog (ТЗ 4.5.2).

Business rules (ranges, dates, program days, flights) are checked in services/tours.py so that
every message is in Ukrainian and PATCH is validated against the merged tour, not just the patch.
Pydantic here only checks types.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import Currency, MealPlan, TourAction, TourStatus, TransportType
from app.schemas.orders import UploadLimitsOut
from app.schemas.reference import CityOut, CountryOut, HotelDetailOut, HotelOut, ResortOut


# ---------- manager input
class ProgramDayIn(BaseModel):
    day_number: int
    description: str


class TourCreate(BaseModel):
    title_uk: str | None = Field(default=None, description="Якщо порожньо — «Готель, Курорт»")
    title_en: str
    hotel_id: int
    transport_type: TransportType
    departure_city_id: int | None = None
    flight_out: str | None = None
    flight_back: str | None = None
    departure_from: date
    departure_to: date
    nights: int
    seats_total: int
    base_price: Decimal
    child_price: Decimal | None = Field(default=None, description="Якщо порожньо — як для дорослого")
    currency: Currency
    description: str | None = None
    is_featured: bool = False
    meal_plan: MealPlan | None = None
    included: list[str] = Field(default=[], description="«Що включено», до 20 пунктів")
    excluded: list[str] = Field(default=[], description="«Що не включено», до 20 пунктів")
    program_days: list[ProgramDayIn] = []


class TourUpdate(BaseModel):
    """All fields optional. `program_days`, if sent, replaces the whole program."""
    title_uk: str | None = None
    title_en: str | None = None
    hotel_id: int | None = None
    transport_type: TransportType | None = None
    departure_city_id: int | None = None
    flight_out: str | None = None
    flight_back: str | None = None
    departure_from: date | None = None
    departure_to: date | None = None
    nights: int | None = None
    seats_total: int | None = None
    base_price: Decimal | None = None
    child_price: Decimal | None = None
    currency: Currency | None = None
    description: str | None = None
    is_featured: bool | None = None
    meal_plan: MealPlan | None = None
    included: list[str] | None = None
    excluded: list[str] | None = None
    program_days: list[ProgramDayIn] | None = None


class ImageOrder(BaseModel):
    image_ids: list[int]


class TourCopyIn(BaseModel):
    """The copy gets new dates (spec 10: the old ones are never copied)."""
    departure_from: date
    departure_to: date


# ---------- output
class ProgramDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_number: int
    description: str


class TourImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int
    file_path: str = Field(exclude=True)

    @computed_field
    @property
    def url(self) -> str:
        return f"/uploads/{self.file_path}"


class TourActionOut(BaseModel):
    """One action of services/tour_actions.py: allowed, or refused with the server's reason."""
    action: TourAction
    allowed: bool
    reason: str | None


class LockedFieldOut(BaseModel):
    """A form field that cannot change now (services/tours.py LOCKED_FIELDS) and why."""
    field: str
    reason: str


class TourStateOut(BaseModel):
    """Actions, locks and the booking numbers the confirmation dialogs show."""
    tour_actions: list[TourActionOut]
    locked_fields: list[LockedFieldOut]
    active_bookings: int = Field(description="Бронювання з чинним утриманням або частково оплачені")
    archive_cancels: int = Field(description="Скільки неоплачених бронювань скасує архівування")
    for_sale: bool = Field(description="Видно в каталозі (той самий критерій, що й у каталозі)")


class ManagerTourHotelOut(BaseModel):
    """The tour's hotel with its resort and country, so the editor shows it even when it was
    archived since (the reference lists hide archived rows)."""
    id: int
    name: str
    stars: int | None
    resort_id: int
    resort_name: str
    country_id: int
    country_name: str
    is_archived: bool = Field(description="Готель, курорт або країна в архіві")


class ManagerTourOut(TourStateOut):
    """Full tour for the back-office form."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: TourStatus
    title_uk: str
    title_en: str
    hotel_id: int
    hotel: ManagerTourHotelOut
    transport_type: TransportType
    departure_city_id: int | None
    flight_out: str | None
    flight_back: str | None
    departure_from: date
    departure_to: date
    nights: int
    seats_total: int
    seats_sold: int
    seats_held: int = Field(description="Місця в бронюваннях з чинним утриманням")
    base_price: Decimal
    child_price: Decimal | None
    currency: Currency
    description: str | None
    is_featured: bool
    meal_plan: MealPlan | None
    included: list[str]
    excluded: list[str]
    created_by: int
    created_at: datetime
    updated_at: datetime
    program_days: list[ProgramDayOut]
    images: list[TourImageOut]


class ManagerTourListItem(TourStateOut):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: TourStatus
    title_uk: str
    hotel_id: int
    hotel_name: str
    resort_name: str
    country_name: str
    image_url: str | None
    departure_from: date
    departure_to: date
    nearest_start: date | None = Field(description="Найближча дата заїзду від завтра; null — дати минули")
    nights: int
    seats_total: int
    seats_sold: int
    free_seats: int
    base_price: Decimal
    currency: Currency
    is_featured: bool
    updated_at: datetime


class TourRulesOut(BaseModel):
    """Limits of the tour form from the backend (the editor checks before sending; the server
    checks again)."""
    photos: UploadLimitsOut
    max_title: int
    max_description: int
    max_day_text: int
    min_nights: int
    max_nights: int
    max_list_items: int
    max_list_item_length: int


class TourCardOut(BaseModel):
    """One tour in the public catalog."""
    id: int
    title_uk: str
    title_en: str
    country: CountryOut
    resort: ResortOut
    hotel: HotelOut
    transport_type: TransportType
    departure_city: CityOut | None
    departure_from: date
    departure_to: date
    nights: int
    currency: Currency
    base_price: Decimal
    price_from_uah: Decimal = Field(description="Ціна «від» за 1 дорослого в гривнях")
    free_seats: int
    is_featured: bool
    meal_plan: MealPlan | None
    image_url: str | None


class FavoriteOut(TourCardOut):
    """A tour in the client's «Обране»: the catalog card, also after the tour left the catalog."""
    for_sale: bool = Field(description="false: тур більше не продається (його сторінка — 404)")
    added_at: datetime


class TourDetailOut(TourCardOut):
    hotel: HotelDetailOut               # the card's hotel + its facts
    child_price: Decimal | None
    child_price_uah: Decimal
    flight_out: str | None
    flight_back: str | None
    description: str | None
    included: list[str]
    excluded: list[str]
    hotel_description: str | None
    program_days: list[ProgramDayOut]
    images: list[TourImageOut]
    # From published reviews (ТЗ 4.5.7); the hotel rating itself is hotel.rating_avg.
    reviews_count: int = 0
    service_rating_avg: Decimal | None = None
