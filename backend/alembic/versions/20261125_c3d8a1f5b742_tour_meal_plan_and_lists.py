"""tour meal plan and lists

Revision ID: c3d8a1f5b742
Revises: b7e2d4a91c55
Create Date: 2026-11-25

feature/catalog-improvements (form 4.6.2.1, new rows):
- tours.meal_plan: board basis ro / bb / hb / fb / ai / uai (VARCHAR + CHECK), NULL = not stated;
- tours.included, tours.excluded: «Що включено» / «Що не включено», TEXT[] (empty by default).
Additive only: existing tours keep working (no meal plan, empty lists).

The catalog's alphabetical sort (sort=title_asc) orders by title_uk COLLATE "uk-x-icu", so that
Є, І, Ї and Ґ fall where the Ukrainian alphabet puts them. That collation comes with PostgreSQL
built with ICU (the Windows installer and the official Docker images are); the migration stops
with a clear message on a server without it instead of failing later on the first sorted request.
Written by hand: autogenerate does not compare CHECK constraints of enums.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d8a1f5b742"
down_revision: str | None = "b7e2d4a91c55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UKRAINIAN_COLLATION = "uk-x-icu"


def upgrade() -> None:
    found = op.get_bind().scalar(sa.text("SELECT count(*) FROM pg_collation WHERE collname = :name"),
                                 {"name": UKRAINIAN_COLLATION})
    if not found:
        raise RuntimeError(
            f'PostgreSQL collation "{UKRAINIAN_COLLATION}" not found: the catalog sorts tour titles '
            f"in Ukrainian alphabetical order with it. Use a PostgreSQL build with ICU support "
            f"(the Windows installer and the official postgres Docker images have it); check with "
            f"SELECT collname FROM pg_collation WHERE collname = '{UKRAINIAN_COLLATION}';")

    op.add_column("tours", sa.Column("meal_plan", sa.String(32), nullable=True))
    op.create_check_constraint(op.f("ck_tours_meal_plan"), "tours",
                               "meal_plan IN ('ro', 'bb', 'hb', 'fb', 'ai', 'uai')")
    op.add_column("tours", sa.Column("included", postgresql.ARRAY(sa.Text()),
                                     server_default="{}", nullable=False))
    op.add_column("tours", sa.Column("excluded", postgresql.ARRAY(sa.Text()),
                                     server_default="{}", nullable=False))


def downgrade() -> None:
    op.drop_column("tours", "excluded")
    op.drop_column("tours", "included")
    op.drop_constraint(op.f("ck_tours_meal_plan"), "tours", type_="check")
    op.drop_column("tours", "meal_plan")
