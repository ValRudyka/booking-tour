"""Read-only reference lists (довідники) used by the catalog filters and the tour form."""
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


class ServiceOptionOut(BaseModel):
    """Insurance or transfer option of the checkout (form 4.6.1.2, fields 4–5)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_uk: str
    price_uah: Decimal   # insurance: per tourist; transfer: per order
    is_default: bool
