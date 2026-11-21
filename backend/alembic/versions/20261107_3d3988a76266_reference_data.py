"""reference data: countries, departure cities, resorts, insurance, transfers, rates, settings

Revision ID: 3d3988a76266
Revises: 7b9314761125
Create Date: 2026-11-07

Plain SQL (not bulk_insert) so that `alembic upgrade --sql` produces a script
that can be run in pgAdmin as is.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "3d3988a76266"
down_revision: str | None = "7b9314761125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def q(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


COUNTRIES = [  # iso, uk, en
    ("UA", "Україна", "Ukraine"), ("PL", "Польща", "Poland"), ("MD", "Молдова", "Moldova"),
    ("TR", "Туреччина", "Turkey"), ("EG", "Єгипет", "Egypt"), ("GR", "Греція", "Greece"),
    ("ES", "Іспанія", "Spain"), ("IT", "Італія", "Italy"), ("ME", "Чорногорія", "Montenegro"),
    ("BG", "Болгарія", "Bulgaria"), ("HR", "Хорватія", "Croatia"), ("CY", "Кіпр", "Cyprus"),
    ("AE", "ОАЕ", "United Arab Emirates"),
]

# Departure cities. Ukrainian airports are closed, so flights depart from
# neighbouring countries; Kyiv and Lviv are bus departure points.
CITIES = [  # country iso, uk, en, iata
    ("UA", "Київ", "Kyiv", None), ("UA", "Львів", "Lviv", None),
    ("PL", "Варшава", "Warsaw", "WAW"), ("PL", "Краків", "Krakow", "KRK"),
    ("PL", "Жешув", "Rzeszow", "RZE"), ("PL", "Катовіце", "Katowice", "KTW"),
    ("MD", "Кишинів", "Chisinau", None),
]

RESORTS = [  # country iso, uk, en
    ("TR", "Анталія", "Antalya"), ("TR", "Аланья", "Alanya"), ("TR", "Кемер", "Kemer"),
    ("TR", "Бодрум", "Bodrum"), ("EG", "Хургада", "Hurghada"),
    ("EG", "Шарм-ель-Шейх", "Sharm El Sheikh"), ("GR", "Крит", "Crete"), ("GR", "Родос", "Rhodes"),
    ("ES", "Коста-Брава", "Costa Brava"), ("ES", "Майорка", "Mallorca"), ("IT", "Ріміні", "Rimini"),
    ("ME", "Будва", "Budva"), ("BG", "Сонячний Берег", "Sunny Beach"),
    ("HR", "Дубровник", "Dubrovnik"), ("CY", "Айя-Напа", "Ayia Napa"), ("AE", "Дубай", "Dubai"),
]

INSURANCE = [("Базове", "350.00", True), ("Розширене", "700.00", False),
             ("Без франшизи", "1000.00", False)]           # price per tourist, UAH
TRANSFERS = [("Груповий", "0.00", True), ("Індивідуальний", "2500.00", False),
             ("VIP", "6000.00", False)]                    # price per order, UAH

# Starting values only; the administrator sets the real commercial rates (form 4.6.4.1).
RATES = [("UAH", "1.0000"), ("EUR", "48.0000"), ("USD", "42.0000")]

SETTINGS = [
    ("acquiring_percent", "2.5"),
    ("booking_timeout_min", "20"),
    ("system_email", '"noreply@tour-website.local"'),
    ("maintenance_mode", "false"),
]


def upgrade() -> None:
    op.execute("INSERT INTO countries (iso_code, name_uk, name_en) VALUES "
               + ", ".join(f"({q(i)}, {q(u)}, {q(e)})" for i, u, e in COUNTRIES))
    op.execute("INSERT INTO cities (country_id, name_uk, name_en, iata_code) VALUES "
               + ", ".join(f"((SELECT id FROM countries WHERE iso_code = {q(c)}), {q(u)}, {q(e)}, {q(i)})"
                           for c, u, e, i in CITIES))
    op.execute("INSERT INTO resorts (country_id, name_uk, name_en) VALUES "
               + ", ".join(f"((SELECT id FROM countries WHERE iso_code = {q(c)}), {q(u)}, {q(e)})"
                           for c, u, e in RESORTS))
    op.execute("INSERT INTO insurance_types (name_uk, price_uah, is_default) VALUES "
               + ", ".join(f"({q(n)}, {p}, {str(d).lower()})" for n, p, d in INSURANCE))
    op.execute("INSERT INTO transfer_types (name_uk, price_uah, is_default) VALUES "
               + ", ".join(f"({q(n)}, {p}, {str(d).lower()})" for n, p, d in TRANSFERS))
    op.execute("INSERT INTO currency_rates (currency, rate_to_uah) VALUES "
               + ", ".join(f"({q(c)}, {r})" for c, r in RATES))
    op.execute("INSERT INTO languages (code, name, is_enabled) VALUES "
               "('uk', 'Українська', true), ('en', 'English', false)")
    op.execute("INSERT INTO settings (key, value) VALUES "
               + ", ".join(f"({q(k)}, {q(v)}::jsonb)" for k, v in SETTINGS))


def downgrade() -> None:
    for table in ("settings", "languages", "currency_rates", "transfer_types", "insurance_types",
                  "resorts", "cities", "countries"):
        op.execute(f"DELETE FROM {table}")
