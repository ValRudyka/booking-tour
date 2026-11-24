-- =====================================================================
-- 10. Resort «Аланья» renamed to «Аланія» (revision b7e2d4a91c55)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 09.
-- Data only: fixes the Ukrainian spelling of one seeded resort in Turkey.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 9a3f6c1d2e84 -> b7e2d4a91c55

UPDATE resorts SET name_uk = 'Аланія' WHERE name_uk = 'Аланья' AND country_id = (SELECT id FROM countries WHERE iso_code = 'TR');

UPDATE alembic_version SET version_num='b7e2d4a91c55' WHERE alembic_version.version_num = '9a3f6c1d2e84';

COMMIT;
