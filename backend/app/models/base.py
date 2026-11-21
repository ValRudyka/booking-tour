"""Declarative base, shared column types and enum helper."""
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable constraint names -> clean Alembic migrations and readable errors.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        Decimal: Numeric(12, 2),
        datetime: DateTime(timezone=True),
    }


def str_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Store a Python enum as VARCHAR + CHECK constraint (not a native PG enum).

    Native enums need ALTER TYPE for every new value; a CHECK constraint is
    simpler to migrate and still rejects invalid values at database level.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
