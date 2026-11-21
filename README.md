# Туристичний вебсайт

Курсовий проєкт: вебсайт туристичної компанії з каталогом турів, онлайн-бронюванням,
оплатою (Stripe, тестовий режим), обробкою заявок менеджером, поверненням коштів і відгуками.
Вимоги — у Технічному завданні (`docs/`).

| Частина | Технології |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Alembic, PostgreSQL 16 |
| Frontend | React, TypeScript, Vite, Tailwind CSS, react-i18next *(з етапу 5)* |
| Тести | pytest |

## Структура

```
tour-website/
├── backend/
│   ├── app/
│   │   ├── main.py        # точка входу FastAPI
│   │   ├── config.py      # налаштування з backend/.env
│   │   ├── db.py          # підключення до БД, сесії
│   │   ├── models/        # таблиці БД (SQLAlchemy)
│   │   ├── schemas/       # Pydantic-схеми запитів/відповідей
│   │   ├── routers/       # ендпоінти API
│   │   ├── services/      # бізнес-логіка (статуси, ціна, квоти)
│   │   └── core/          # безпека: JWT, паролі, ролі
│   ├── alembic/versions/  # міграції БД (джерело правди про схему)
│   ├── scripts/           # службові скрипти (генерація ER-діаграми)
│   └── tests/
├── database/              # SQL-скрипти для ручного запуску в pgAdmin
└── docs/                  # ER-діаграма
```

## Перший запуск (Windows)

### 1. База даних (pgAdmin)

1. Підключіться до сервера як `postgres`, відкрийте **Query Tool** на базі `postgres`.
2. Відкрийте `database/01_create_roles_and_databases.sql`, **замініть пароль**
   і виконайте **три блоки по черзі** (виділити блок → F5).
3. У дереві pgAdmin натисніть *Refresh*, з'являться бази `tour_website` і `tour_website_test`.

Далі таблиці можна створити **одним із двох способів** (обидва дають однаковий результат):

- **Спосіб А — Alembic (рекомендовано):** див. крок 3 нижче, команда `alembic upgrade head`.
- **Спосіб Б — SQL-скрипти в pgAdmin:** створіть у pgAdmin нове підключення до бази
  `tour_website` **від імені користувача `tour_app`** і виконайте по черзі
  `database/02_schema.sql`, потім `database/03_reference_data.sql`.
  Скрипти також записують версію в таблицю `alembic_version`, тож надалі
  нові міграції застосовуються звичайною командою `alembic upgrade head`.

### 2. Python-середовище

```bash
conda create -n tour python=3.12
conda activate tour
cd backend
pip install -r requirements.txt
copy .env.example .env      # і впишіть свій пароль у DATABASE_URL та TEST_DATABASE_URL
```

### 3. Міграції, тести, запуск

```bash
alembic upgrade head        # створює/оновлює таблиці (пропустіть, якщо виконали спосіб Б)
pytest                      # тести працюють з базою tour_website_test
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Документація Swagger: http://127.0.0.1:8000/docs
- Перевірка: http://127.0.0.1:8000/health → `{"status":"ok","database":"ok"}`

## База даних

27 таблиць, 37 зв'язків, 34 іменовані CHECK-обмеження. Схема описана в `app/models/`,
усі зміни — тільки через міграції:

```bash
# після зміни моделей
alembic revision --autogenerate -m "опис зміни"
alembic upgrade head
alembic check                 # перевірка: моделі і БД збігаються

# оновити ER-діаграму з моделей
python -m scripts.generate_er # -> docs/er_diagram.puml

# оновити SQL-скрипти для pgAdmin
alembic upgrade base:head --sql > ../database/schema_full.sql
```

Статуси замовлення, оплати та туру відповідають розділу 4.4.1 ТЗ
(`app/models/enums.py`). Значення зберігаються як `VARCHAR` + `CHECK`,
тому база сама відхиляє невідомий статус.

## Етапи

- [x] 1. ER-діаграма
- [x] 2. Каркас проєкту, моделі, міграції, довідники, тести схеми
- [ ] 3. Автентифікація (JWT) і ролі
- [ ] 4. Тури та каталог (пошук, фільтри, сортування)
- [ ] 5. Замовлення: чекаут, утримання квоти, статуси
- [ ] 6. Оплата Stripe (test mode) і повернення коштів
- [ ] 7. Обробка заявок менеджером, документи, відгуки
- [ ] 8. Адміністрування: користувачі, довідники, налаштування
- [ ] 9. Frontend
- [ ] 10. Додаткові функції (обране, історія пошуку, лояльність, звіти, e-mail, моніторинг)
