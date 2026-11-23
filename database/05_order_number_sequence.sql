-- =====================================================================
-- 05. Order number sequence and offer acceptance (revision 165a48e92881)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app"
-- (so tour_app owns the new objects), after 02 and 03. Open Query Tool -> paste/open file -> F5.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 3d3988a76266 -> 165a48e92881

CREATE SEQUENCE order_number_seq START WITH 1;

ALTER TABLE orders ADD COLUMN offer_accepted_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='165a48e92881' WHERE alembic_version.version_num = '3d3988a76266';

COMMIT;

