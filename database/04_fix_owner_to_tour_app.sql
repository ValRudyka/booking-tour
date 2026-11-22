-- =====================================================================
-- 04. Fix: tables were created as "postgres" instead of "tour_app"
--
-- Symptom:  SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public';
--           returns "postgres"; the app fails with "permission denied for table ...".
-- Effect:   gives every table (and its id sequences, indexes, constraints)
--           to tour_app. ALL DATA IS KEPT.
--
-- Run in pgAdmin connected AS "postgres" to the database "tour_website".
-- Select nothing and press F5 (runs as one transaction).
-- =====================================================================

BEGIN;

-- The database itself must belong to tour_app too
ALTER DATABASE tour_website OWNER TO tour_app;

-- Every table in schema public. Sequences behind id columns and all indexes
-- follow their table automatically.
DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables
             WHERE schemaname = 'public' AND tableowner <> 'tour_app'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO tour_app', t.tablename);
    END LOOP;
END $$;

COMMIT;

-- Check (both must return only tour_app):
SELECT DISTINCT tableowner AS table_owner FROM pg_tables WHERE schemaname = 'public';
SELECT DISTINCT pg_get_userbyid(c.relowner) AS sequence_owner
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S' AND n.nspname = 'public';
