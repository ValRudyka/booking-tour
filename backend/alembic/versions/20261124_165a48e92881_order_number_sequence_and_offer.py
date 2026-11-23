"""order number sequence and offer acceptance

Revision ID: 165a48e92881
Revises: 3d3988a76266
Create Date: 2026-11-24

- order_number_seq: source of order numbers TU-<year>-<nnnnnn> (atomic under concurrent
  checkouts, value known before the INSERT). Alembic autogenerate does not compare sequences,
  so it is written here by hand.
- orders.offer_accepted_at: when the client accepted the public offer (form 4.6.1.2, field 9).
Only adds objects; existing data is not touched.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "165a48e92881"
down_revision: str | None = "3d3988a76266"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE order_number_seq START WITH 1")
    op.add_column("orders", sa.Column("offer_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "offer_accepted_at")
    op.execute("DROP SEQUENCE order_number_seq")
