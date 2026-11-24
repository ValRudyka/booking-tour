"""bank transfer hold setting

Revision ID: 2d155601a7cd
Revises: 165a48e92881
Create Date: 2026-11-24

Data only (no schema change): adds the global setting `bank_transfer_hold_hours` = 48.
Choosing a bank transfer extends the order's seat hold to this many hours, because a transfer
takes days, not minutes. Kept in `settings` next to `booking_timeout_min`, so the admin can
change it later (feature/admin). Plain SQL so `alembic upgrade --sql` gives a pgAdmin script.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "2d155601a7cd"
down_revision: str | None = "165a48e92881"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("INSERT INTO settings (key, value) VALUES ('bank_transfer_hold_hours', '48'::jsonb) "
               "ON CONFLICT (key) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'bank_transfer_hold_hours'")
