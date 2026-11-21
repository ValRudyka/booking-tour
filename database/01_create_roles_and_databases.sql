-- =====================================================================
-- Tour website: database user and databases
-- Run ONCE in pgAdmin, connected as the superuser "postgres"
-- (Query Tool on the "postgres" database).
--
-- pgAdmin runs CREATE DATABASE outside a transaction only when it is the
-- single statement executed, so run the three blocks ONE BY ONE:
-- select a block -> F5 (Execute script) or "Execute/Refresh".
-- =====================================================================

-- Block 1. Application user. Replace the password and keep it for .env
CREATE ROLE tour_app WITH LOGIN PASSWORD 'change_me';

-- Block 2. Main database
CREATE DATABASE tour_website OWNER tour_app ENCODING 'UTF8' TEMPLATE template0;

-- Block 3. Database for automated tests (pytest wipes it)
CREATE DATABASE tour_website_test OWNER tour_app ENCODING 'UTF8' TEMPLATE template0;
