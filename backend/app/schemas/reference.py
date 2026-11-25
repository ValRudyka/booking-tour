"""Read-only reference lists (довідники) used by the catalog filters and the tour form."""
from datetime import time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CountryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iso_code: str
    name_uk: str
    name_en: str | None


class ResortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    country_id: int
    name_uk: str
    name_en: str | None


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    country_id: int
    name_uk: str
    name_en: str | None
    iata_code: str | None


class HotelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resort_id: int
    name: str
    stars: int | None
    rating_avg: Decimal | None


class HotelDetailOut(HotelOut):
    """The hotel on the tour page: HotelOut + facts (form 4.6.4.2). Catalog cards and reference
    lists keep the light HotelOut, so a page of cards carries no amenity lists."""
    beach_line: int | None
    distance_to_beach_m: int | None
    distance_to_airport_km: int | None
    check_in: time | None
    check_out: time | None
    amenities: list[str]
    room_types: list[str]


class ServiceOptionOut(BaseModel):
    """Insurance or transfer option of the checkout (form 4.6.1.2, fields 4–5)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_uk: str
    price_uah: Decimal   # insurance: per tourist; transfer: per order
    is_default: bool
