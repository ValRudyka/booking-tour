-- =====================================================================
-- 06. Setting bank_transfer_hold_hours = 48 (revision 2d155601a7cd)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 05.
-- Data only: adds one row to the settings table.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 165a48e92881 -> 2d155601a7cd

INSERT INTO settings (key, value) VALUES ('bank_transfer_hold_hours', '48'::jsonb) ON CONFLICT (key) DO NOTHING;

UPDATE alembic_version SET version_num='2d155601a7cd' WHERE alembic_version.version_num = '165a48e92881';

COMMIT;

