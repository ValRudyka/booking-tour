"""review moderation

Revision ID: e5b19c3f7a20
Revises: 8c41e7d2a9b3
Create Date: 2026-11-24

feature/reviews (ТЗ 4.5.7, form 4.6.1.4):
- reviews.status (pending / published / rejected) replaces is_published: true -> published,
  false -> pending;
- reviews.reject_reason, moderated_by, moderated_at: who decided, when and why;
- reviews.submitted_at (queue order), resubmitted_at (the one allowed correction), updated_at;
- reviews.hotel_id: the hotel the client stayed in, filled from the tour; saved on the review so a
  later change of the tour's hotel does not move reviews or ratings;
- setting review_premoderation = true (ТЗ 4.5.7 step 6: moderation "or at once, by settings").
Written by hand: autogenerate does not compare CHECK constraints of enums.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b19c3f7a20"
down_revision: str | None = "8c41e7d2a9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("status", sa.String(32), server_default="pending", nullable=False))
    op.create_check_constraint(op.f("ck_reviews_review_status"), "reviews",
                               "status IN ('pending', 'published', 'rejected')")
    op.execute("UPDATE reviews SET status = 'published' WHERE is_published")
    op.drop_column("reviews", "is_published")
    op.create_index(op.f("ix_reviews_status"), "reviews", ["status"])

    op.add_column("reviews", sa.Column("hotel_id", sa.Integer(), nullable=True))
    op.execute("UPDATE reviews AS r SET hotel_id = t.hotel_id FROM tours AS t WHERE t.id = r.tour_id")
    op.alter_column("reviews", "hotel_id", nullable=False)
    op.create_foreign_key(op.f("fk_reviews_hotel_id_hotels"), "reviews", "hotels", ["hotel_id"], ["id"])
    op.create_index(op.f("ix_reviews_hotel_id"), "reviews", ["hotel_id"])

    op.add_column("reviews", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("moderated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(op.f("fk_reviews_moderated_by_users"), "reviews", "users",
                          ["moderated_by"], ["id"])
    op.add_column("reviews", sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reviews", sa.Column("submitted_at", sa.DateTime(timezone=True),
                                       server_default=sa.text("now()"), nullable=False))
    op.execute("UPDATE reviews SET submitted_at = created_at")
    op.add_column("reviews", sa.Column("resubmitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reviews", sa.Column("updated_at", sa.DateTime(timezone=True),
                                       server_default=sa.text("now()"), nullable=False))

    op.execute("INSERT INTO settings (key, value) VALUES ('review_premoderation', 'true'::jsonb) "
               "ON CONFLICT (key) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'review_premoderation'")
    op.drop_column("reviews", "updated_at")
    op.drop_column("reviews", "resubmitted_at")
    op.drop_column("reviews", "submitted_at")
    op.drop_column("reviews", "moderated_at")
    op.drop_constraint(op.f("fk_reviews_moderated_by_users"), "reviews", type_="foreignkey")
    op.drop_column("reviews", "moderated_by")
    op.drop_column("reviews", "reject_reason")
    op.drop_index(op.f("ix_reviews_hotel_id"), table_name="reviews")
    op.drop_constraint(op.f("fk_reviews_hotel_id_hotels"), "reviews", type_="foreignkey")
    op.drop_column("reviews", "hotel_id")
    op.add_column("reviews", sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False))
    op.execute("UPDATE reviews SET is_published = (status = 'published')")
    op.drop_index(op.f("ix_reviews_status"), table_name="reviews")
    op.drop_constraint(op.f("ck_reviews_review_status"), "reviews", type_="check")
    op.drop_column("reviews", "status")
