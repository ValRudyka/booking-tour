-- =====================================================================
-- 03. Reference data: countries, departure cities, resorts, insurance, transfers, rates, languages, settings (revision 3d3988a76266)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app"
-- (so tour_app owns the tables). Open Query Tool -> paste/open file -> F5.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 7b9314761125 -> 3d3988a76266

INSERT INTO countries (iso_code, name_uk, name_en) VALUES ('UA', 'Україна', 'Ukraine'), ('PL', 'Польща', 'Poland'), ('MD', 'Молдова', 'Moldova'), ('TR', 'Туреччина', 'Turkey'), ('EG', 'Єгипет', 'Egypt'), ('GR', 'Греція', 'Greece'), ('ES', 'Іспанія', 'Spain'), ('IT', 'Італія', 'Italy'), ('ME', 'Чорногорія', 'Montenegro'), ('BG', 'Болгарія', 'Bulgaria'), ('HR', 'Хорватія', 'Croatia'), ('CY', 'Кіпр', 'Cyprus'), ('AE', 'ОАЕ', 'United Arab Emirates');

INSERT INTO cities (country_id, name_uk, name_en, iata_code) VALUES ((SELECT id FROM countries WHERE iso_code = 'UA'), 'Київ', 'Kyiv', NULL), ((SELECT id FROM countries WHERE iso_code = 'UA'), 'Львів', 'Lviv', NULL), ((SELECT id FROM countries WHERE iso_code = 'PL'), 'Варшава', 'Warsaw', 'WAW'), ((SELECT id FROM countries WHERE iso_code = 'PL'), 'Краків', 'Krakow', 'KRK'), ((SELECT id FROM countries WHERE iso_code = 'PL'), 'Жешув', 'Rzeszow', 'RZE'), ((SELECT id FROM countries WHERE iso_code = 'PL'), 'Катовіце', 'Katowice', 'KTW'), ((SELECT id FROM countries WHERE iso_code = 'MD'), 'Кишинів', 'Chisinau', NULL);

INSERT INTO resorts (country_id, name_uk, name_en) VALUES ((SELECT id FROM countries WHERE iso_code = 'TR'), 'Анталія', 'Antalya'), ((SELECT id FROM countries WHERE iso_code = 'TR'), 'Аланья', 'Alanya'), ((SELECT id FROM countries WHERE iso_code = 'TR'), 'Кемер', 'Kemer'), ((SELECT id FROM countries WHERE iso_code = 'TR'), 'Бодрум', 'Bodrum'), ((SELECT id FROM countries WHERE iso_code = 'EG'), 'Хургада', 'Hurghada'), ((SELECT id FROM countries WHERE iso_code = 'EG'), 'Шарм-ель-Шейх', 'Sharm El Sheikh'), ((SELECT id FROM countries WHERE iso_code = 'GR'), 'Крит', 'Crete'), ((SELECT id FROM countries WHERE iso_code = 'GR'), 'Родос', 'Rhodes'), ((SELECT id FROM countries WHERE iso_code = 'ES'), 'Коста-Брава', 'Costa Brava'), ((SELECT id FROM countries WHERE iso_code = 'ES'), 'Майорка', 'Mallorca'), ((SELECT id FROM countries WHERE iso_code = 'IT'), 'Ріміні', 'Rimini'), ((SELECT id FROM countries WHERE iso_code = 'ME'), 'Будва', 'Budva'), ((SELECT id FROM countries WHERE iso_code = 'BG'), 'Сонячний Берег', 'Sunny Beach'), ((SELECT id FROM countries WHERE iso_code = 'HR'), 'Дубровник', 'Dubrovnik'), ((SELECT id FROM countries WHERE iso_code = 'CY'), 'Айя-Напа', 'Ayia Napa'), ((SELECT id FROM countries WHERE iso_code = 'AE'), 'Дубай', 'Dubai');

INSERT INTO insurance_types (name_uk, price_uah, is_default) VALUES ('Базове', 350.00, true), ('Розширене', 700.00, false), ('Без франшизи', 1000.00, false);

INSERT INTO transfer_types (name_uk, price_uah, is_default) VALUES ('Груповий', 0.00, true), ('Індивідуальний', 2500.00, false), ('VIP', 6000.00, false);

INSERT INTO currency_rates (currency, rate_to_uah) VALUES ('UAH', 1.0000), ('EUR', 48.0000), ('USD', 42.0000);

INSERT INTO languages (code, name, is_enabled) VALUES ('uk', 'Українська', true), ('en', 'English', false);

INSERT INTO settings (key, value) VALUES ('acquiring_percent', '2.5'::jsonb), ('booking_timeout_min', '20'::jsonb), ('system_email', '"noreply@tour-website.local"'::jsonb), ('maintenance_mode', 'false'::jsonb);

UPDATE alembic_version SET version_num='3d3988a76266' WHERE alembic_version.version_num = '7b9314761125';

COMMIT;

