"""refunds and cancellation requests

Revision ID: 8c41e7d2a9b3
Revises: 2d155601a7cd
Create Date: 2026-11-24

feature/order-processing (ТЗ 4.5.4–4.5.6, forms 4.6.1.3, 4.6.3.1):
- payments.refund_of_id: a refund row points at the payment it returns money from (needed when an
  order has several payments). Existing automatic late-payment refunds are linked to their card
  payment by the shared Stripe PaymentIntent.
- payments.stripe_refund_id becomes unique: refund webhooks find the row by it.
- orders.fpv_uah: ФПВ kept when the refund was made.
- orders.cancel_reason_code: reason from the list «Причини скасувань» (form 4.6.1.3, field 2).
- order_documents.doc_type gets 'cancel_evidence' (client's supporting files, field 4).
Written by hand: autogenerate does not compare CHECK constraints of enums.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c41e7d2a9b3"
down_revision: str | None = "2d155601a7cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DOC_TYPES = "'voucher', 'air_ticket', 'insurance_policy', 'info_sheet'"
NEW_DOC_TYPES = OLD_DOC_TYPES + ", 'cancel_evidence'"
CANCEL_REASONS = "'illness', 'change_of_plans', 'data_error', 'visa_refusal', 'other'"


def upgrade() -> None:
    op.add_column("payments", sa.Column("refund_of_id", sa.Integer(), nullable=True))
    op.create_foreign_key(op.f("fk_payments_refund_of_id_payments"), "payments", "payments",
                          ["refund_of_id"], ["id"])
    op.create_index(op.f("ix_payments_refund_of_id"), "payments", ["refund_of_id"])
    op.create_check_constraint(op.f("ck_payments_refund_of_only_refunds"), "payments",
                               "type = 'refund' OR refund_of_id IS NULL")
    op.create_unique_constraint(op.f("uq_payments_stripe_refund_id"), "payments", ["stripe_refund_id"])
    # Link the refunds that already exist (automatic late-payment refunds of card payments).
    op.execute("""
        UPDATE payments AS r SET refund_of_id = p.id
        FROM payments AS p
        WHERE r.type = 'refund' AND r.refund_of_id IS NULL
          AND p.type = 'payment' AND p.order_id = r.order_id
          AND p.stripe_payment_intent IS NOT NULL
          AND p.stripe_payment_intent = r.stripe_payment_intent
    """)

    op.add_column("orders", sa.Column("fpv_uah", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(op.f("ck_orders_fpv_non_negative"), "orders",
                               "fpv_uah IS NULL OR fpv_uah >= 0")
    op.add_column("orders", sa.Column("cancel_reason_code", sa.String(32), nullable=True))
    op.create_check_constraint(op.f("ck_orders_cancel_reason"), "orders",
                               f"cancel_reason_code IN ({CANCEL_REASONS})")

    op.drop_constraint(op.f("ck_order_documents_order_document_type"), "order_documents", type_="check")
    op.create_check_constraint(op.f("ck_order_documents_order_document_type"), "order_documents",
                               f"doc_type IN ({NEW_DOC_TYPES})")


def downgrade() -> None:
    op.execute("DELETE FROM order_documents WHERE doc_type = 'cancel_evidence'")
    op.drop_constraint(op.f("ck_order_documents_order_document_type"), "order_documents", type_="check")
    op.create_check_constraint(op.f("ck_order_documents_order_document_type"), "order_documents",
                               f"doc_type IN ({OLD_DOC_TYPES})")
    op.drop_constraint(op.f("ck_orders_cancel_reason"), "orders", type_="check")
    op.drop_column("orders", "cancel_reason_code")
    op.drop_constraint(op.f("ck_orders_fpv_non_negative"), "orders", type_="check")
    op.drop_column("orders", "fpv_uah")
    op.drop_constraint(op.f("uq_payments_stripe_refund_id"), "payments", type_="unique")
    op.drop_constraint(op.f("ck_payments_refund_of_only_refunds"), "payments", type_="check")
    op.drop_index(op.f("ix_payments_refund_of_id"), table_name="payments")
    op.drop_constraint(op.f("fk_payments_refund_of_id_payments"), "payments", type_="foreignkey")
    op.drop_column("payments", "refund_of_id")
