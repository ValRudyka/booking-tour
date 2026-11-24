-- =====================================================================
-- 08. Review moderation (revision e5b19c3f7a20)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 07.
-- reviews: status (pending/published/rejected) instead of is_published, hotel_id, reject_reason,
-- moderated_by/at, submitted_at, resubmitted_at, updated_at; setting review_premoderation = true.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 8c41e7d2a9b3 -> e5b19c3f7a20

ALTER TABLE reviews ADD COLUMN status VARCHAR(32) DEFAULT 'pending' NOT NULL;

ALTER TABLE reviews ADD CONSTRAINT ck_reviews_review_status CHECK (status IN ('pending', 'published', 'rejected'));

UPDATE reviews SET status = 'published' WHERE is_published;

ALTER TABLE reviews DROP COLUMN is_published;

CREATE INDEX ix_reviews_status ON reviews (status);

ALTER TABLE reviews ADD COLUMN hotel_id INTEGER;

UPDATE reviews AS r SET hotel_id = t.hotel_id FROM tours AS t WHERE t.id = r.tour_id;

ALTER TABLE reviews ALTER COLUMN hotel_id SET NOT NULL;

ALTER TABLE reviews ADD CONSTRAINT fk_reviews_hotel_id_hotels FOREIGN KEY(hotel_id) REFERENCES hotels (id);

CREATE INDEX ix_reviews_hotel_id ON reviews (hotel_id);

ALTER TABLE reviews ADD COLUMN reject_reason TEXT;

ALTER TABLE reviews ADD COLUMN moderated_by INTEGER;

ALTER TABLE reviews ADD CONSTRAINT fk_reviews_moderated_by_users FOREIGN KEY(moderated_by) REFERENCES users (id);

ALTER TABLE reviews ADD COLUMN moderated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE reviews ADD COLUMN submitted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

UPDATE reviews SET submitted_at = created_at;

ALTER TABLE reviews ADD COLUMN resubmitted_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE reviews ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

INSERT INTO settings (key, value) VALUES ('review_premoderation', 'true'::jsonb) ON CONFLICT (key) DO NOTHING;

UPDATE alembic_version SET version_num='e5b19c3f7a20' WHERE alembic_version.version_num = '8c41e7d2a9b3';

COMMIT;

