-- =====================================================================
-- 11. Catalog improvements (revisions c3d8a1f5b742, d9f2b6c4e815, e1a7c0b3f926)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 10.
-- Additive only: tours.meal_plan / included / excluded, hotel facts, payments.origin.
-- Needs the ICU collation "uk-x-icu" (Ukrainian title sort): the first statement stops the
-- script with a clear message on a PostgreSQL built without ICU.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade b7e2d4a91c55 -> c3d8a1f5b742

DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_collation WHERE collname = 'uk-x-icu') THEN RAISE EXCEPTION 'PostgreSQL collation "uk-x-icu" not found: the catalog sorts tour titles in Ukrainian alphabetical order with it. Use a PostgreSQL build with ICU support (the Windows installer and the official postgres Docker images have it); check with SELECT collname FROM pg_collation WHERE collname = ''uk-x-icu'';'; END IF; END $$;

ALTER TABLE tours ADD COLUMN meal_plan VARCHAR(32);

ALTER TABLE tours ADD CONSTRAINT ck_tours_meal_plan CHECK (meal_plan IN ('ro', 'bb', 'hb', 'fb', 'ai', 'uai'));

ALTER TABLE tours ADD COLUMN included TEXT[] DEFAULT '{}' NOT NULL;

ALTER TABLE tours ADD COLUMN excluded TEXT[] DEFAULT '{}' NOT NULL;

UPDATE alembic_version SET version_num='c3d8a1f5b742' WHERE alembic_version.version_num = 'b7e2d4a91c55';

-- Running upgrade c3d8a1f5b742 -> d9f2b6c4e815

ALTER TABLE hotels ADD COLUMN beach_line SMALLINT;

ALTER TABLE hotels ADD COLUMN distance_to_beach_m INTEGER;

ALTER TABLE hotels ADD COLUMN distance_to_airport_km INTEGER;

ALTER TABLE hotels ADD COLUMN check_in TIME WITHOUT TIME ZONE;

ALTER TABLE hotels ADD COLUMN check_out TIME WITHOUT TIME ZONE;

ALTER TABLE hotels ADD COLUMN amenities TEXT[] DEFAULT '{}' NOT NULL;

ALTER TABLE hotels ADD COLUMN room_types TEXT[] DEFAULT '{}' NOT NULL;

ALTER TABLE hotels ADD CONSTRAINT ck_hotels_beach_line_range CHECK (beach_line BETWEEN 1 AND 5);

ALTER TABLE hotels ADD CONSTRAINT ck_hotels_distance_to_beach_non_negative CHECK (distance_to_beach_m >= 0);

ALTER TABLE hotels ADD CONSTRAINT ck_hotels_distance_to_airport_non_negative CHECK (distance_to_airport_km >= 0);

UPDATE alembic_version SET version_num='d9f2b6c4e815' WHERE alembic_version.version_num = 'c3d8a1f5b742';

-- Running upgrade d9f2b6c4e815 -> e1a7c0b3f926

ALTER TABLE payments ADD COLUMN origin VARCHAR(32) DEFAULT 'app' NOT NULL;

ALTER TABLE payments ADD CONSTRAINT ck_payments_payment_origin CHECK (origin IN ('app', 'demo_seed'));

CREATE INDEX ix_payments_origin ON payments (origin);

UPDATE alembic_version SET version_num='e1a7c0b3f926' WHERE alembic_version.version_num = 'd9f2b6c4e815';

COMMIT;

