"""hotel facts

Revision ID: d9f2b6c4e815
Revises: c3d8a1f5b742
Create Date: 2026-11-25

feature/catalog-improvements (hotel reference form 4.6.4.2, added to the ТЗ in this branch):
structured hotel facts for the tour page instead of lines in the description. All optional and
additive: existing hotels keep working with NULL / empty values.
- beach_line 1–5, distance_to_beach_m >= 0 (0 = on the beach), distance_to_airport_km >= 0;
- check_in / check_out (TIME);
- amenities, room_types (TEXT[], empty by default).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9f2b6c4e815"
down_revision: str | None = "c3d8a1f5b742"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hotels", sa.Column("beach_line", sa.SmallInteger(), nullable=True))
    op.add_column("hotels", sa.Column("distance_to_beach_m", sa.Integer(), nullable=True))
    op.add_column("hotels", sa.Column("distance_to_airport_km", sa.Integer(), nullable=True))
    op.add_column("hotels", sa.Column("check_in", sa.Time(), nullable=True))
    op.add_column("hotels", sa.Column("check_out", sa.Time(), nullable=True))
    op.add_column("hotels", sa.Column("amenities", postgresql.ARRAY(sa.Text()),
                                      server_default="{}", nullable=False))
    op.add_column("hotels", sa.Column("room_types", postgresql.ARRAY(sa.Text()),
                                      server_default="{}", nullable=False))
    op.create_check_constraint(op.f("ck_hotels_beach_line_range"), "hotels", "beach_line BETWEEN 1 AND 5")
    op.create_check_constraint(op.f("ck_hotels_distance_to_beach_non_negative"), "hotels",
                               "distance_to_beach_m >= 0")
    op.create_check_constraint(op.f("ck_hotels_distance_to_airport_non_negative"), "hotels",
                               "distance_to_airport_km >= 0")


def downgrade() -> None:
    for name in ("distance_to_airport_non_negative", "distance_to_beach_non_negative", "beach_line_range"):
        op.drop_constraint(op.f(f"ck_hotels_{name}"), "hotels", type_="check")
    for column in ("room_types", "amenities", "check_out", "check_in", "distance_to_airport_km",
                   "distance_to_beach_m", "beach_line"):
        op.drop_column("hotels", column)
