"""admin: token cut-off, single default services, append-only audit log

Revision ID: 9a3f6c1d2e84
Revises: e5b19c3f7a20
Create Date: 2026-11-24

feature/admin (ТЗ 4.3, 4.5.8, form 4.6.4.1, ТЗ 7):
- users.tokens_valid_after: tokens issued before it are rejected (admin password reset);
- partial unique indexes: at most one default insurance type and one default transfer type;
- audit_log is append-only: a trigger refuses UPDATE and DELETE (ТЗ 7: the log is protected
  from changes). TRUNCATE / DROP by the table owner are not covered — that is a DBA's tool,
  not something the application can do by mistake.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a3f6c1d2e84"
down_revision: str | None = "e5b19c3f7a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True))
    for table in ("insurance_types", "transfer_types"):
        op.create_index(f"uq_{table}_single_default", table, ["is_default"], unique=True,
                        postgresql_where=sa.text("is_default"))
    op.execute("""
        CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
               "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()")


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION audit_log_append_only()")
    for table in ("insurance_types", "transfer_types"):
        op.drop_index(f"uq_{table}_single_default", table_name=table)
    op.drop_column("users", "tokens_valid_after")
