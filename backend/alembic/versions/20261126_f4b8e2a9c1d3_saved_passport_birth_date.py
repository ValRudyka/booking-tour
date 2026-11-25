"""saved passport birth date

Revision ID: f4b8e2a9c1d3
Revises: e1a7c0b3f926
Create Date: 2026-11-26

feature/frontend-client-profile (spec 08): a saved tourist (form 4.6.1.1, field 8) also keeps the
birth date, so «Збережений паспорт» at checkout fills every tourist field (form 4.6.1.2, 3.6).
Nullable: rows saved before have none; the API requires it for new and edited ones.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b8e2a9c1d3"
down_revision: str | None = "e1a7c0b3f926"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("saved_passports", sa.Column("birth_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("saved_passports", "birth_date")
