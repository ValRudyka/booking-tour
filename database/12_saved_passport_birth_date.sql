-- =====================================================================
-- 12. Saved passport birth date (revision f4b8e2a9c1d3)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 11.
-- Additive only: saved_passports.birth_date (nullable; rows saved before have none).
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade e1a7c0b3f926 -> f4b8e2a9c1d3

ALTER TABLE saved_passports ADD COLUMN birth_date DATE;

UPDATE alembic_version SET version_num='f4b8e2a9c1d3' WHERE alembic_version.version_num = 'e1a7c0b3f926';

COMMIT;

