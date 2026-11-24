"""Promo codes managed by managers (form 4.6.2.3)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import DiscountType


class PromoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str                           # field 1: 4–20 Latin letters and digits
    discount_type: DiscountType         # field 2
    discount_value: Decimal             # field 3: percent 1–100 or UAH
    min_order_uah: Decimal | None = None   # field 4
    valid_from: date                    # field 5
    valid_to: date                      # field 6: later than valid_from
    usage_limit: int | None = None      # field 7: empty = no limit
    is_active: bool = True              # field 9


class PromoPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")   # used_count / paid_count are read-only

    code: str | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    min_order_uah: Decimal | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    usage_limit: int | None = None
    is_active: bool | None = None


class PromoOut(BaseModel):
    id: int
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    min_order_uah: Decimal | None
    valid_from: date
    valid_to: date
    usage_limit: int | None
    is_active: bool
    used_count: int                     # holds a use now (the limit counter)
    paid_count: int                     # field 8: paid orders with this code
    created_by: int
    created_at: datetime
