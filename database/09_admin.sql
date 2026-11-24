-- =====================================================================
-- 09. Administration (revision 9a3f6c1d2e84)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 08.
-- users.tokens_valid_after; one default insurance / transfer type (partial unique indexes);
-- audit_log becomes append-only (trigger refuses UPDATE and DELETE).
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade e5b19c3f7a20 -> 9a3f6c1d2e84

ALTER TABLE users ADD COLUMN tokens_valid_after TIMESTAMP WITH TIME ZONE;

CREATE UNIQUE INDEX uq_insurance_types_single_default ON insurance_types (is_default) WHERE is_default;

CREATE UNIQUE INDEX uq_transfer_types_single_default ON transfer_types (is_default) WHERE is_default;

CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

UPDATE alembic_version SET version_num='9a3f6c1d2e84' WHERE alembic_version.version_num = 'e5b19c3f7a20';

COMMIT;

