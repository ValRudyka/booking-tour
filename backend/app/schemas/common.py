"""Schemas shared by several routers."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a list: `total` is the number of rows matching the filters."""
    items: list[T]
    total: int
    page: int
    page_size: int
