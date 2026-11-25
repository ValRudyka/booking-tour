"""payment origin

Revision ID: e1a7c0b3f926
Revises: d9f2b6c4e815
Create Date: 2026-11-25

feature/catalog-improvements: payments.origin tells real money movements from demo data.
- app: made by the application (Stripe test mode, mock gateway, bank transfer) — every existing row;
- demo_seed: written by scripts.seed_demo for demo orders; no money moved.
The finance register returns it and can filter by it; reports must leave demo_seed out.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a7c0b3f926"
down_revision: str | None = "d9f2b6c4e815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("origin", sa.String(32), server_default="app", nullable=False))
    op.create_check_constraint(op.f("ck_payments_payment_origin"), "payments",
                               "origin IN ('app', 'demo_seed')")
    op.create_index(op.f("ix_payments_origin"), "payments", ["origin"])


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_origin"), "payments")
    op.drop_constraint(op.f("ck_payments_payment_origin"), "payments", type_="check")
    op.drop_column("payments", "origin")
