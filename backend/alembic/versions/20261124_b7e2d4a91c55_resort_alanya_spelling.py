"""resort Alanya spelling

Revision ID: b7e2d4a91c55
Revises: 9a3f6c1d2e84
Create Date: 2026-11-24

Data only (no schema change): the seeded resort «Аланья» (a Russian-style spelling) becomes
«Аланія», the Ukrainian spelling used by the rest of the site and by the demo hotels. Only the row
with the old spelling in Turkey is touched, so a name the admin has already changed stays as it is.
Plain SQL so `alembic upgrade --sql` gives a pgAdmin script.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b7e2d4a91c55"
down_revision: str | None = "9a3f6c1d2e84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TURKEY = "(SELECT id FROM countries WHERE iso_code = 'TR')"


def upgrade() -> None:
    op.execute(f"UPDATE resorts SET name_uk = 'Аланія' "
               f"WHERE name_uk = 'Аланья' AND country_id = {TURKEY}")


def downgrade() -> None:
    op.execute(f"UPDATE resorts SET name_uk = 'Аланья' "
               f"WHERE name_uk = 'Аланія' AND country_id = {TURKEY}")
