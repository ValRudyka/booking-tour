# CLAUDE.md — Tour website (course project)

Solo course project: a tour company website with catalog, online booking, Stripe test-mode
payments, manager processing, refunds and reviews. The full requirements are in the
technical specification (ТЗ): `docs/tz/TZ_tour_website_v2.md` (Markdown, searchable) and
`docs/tz/TZ_tour_website_v2.docx` (the official document). **Read the relevant ТЗ section
before implementing a feature** — section numbers are referenced throughout the code.

The owner is a student (Python/SQL confident, React intermediate) who must defend the
project: explain non-obvious decisions briefly in code comments and PR descriptions.

## Working rules (from the owner — follow them)

- **Do everything the ТЗ describes**, in the backlog order below. Do not drop features
  because of deadlines; a working end-to-end demo must exist after every merged feature.
- **Check the official documentation of each library before using it** (APIs change;
  e.g. FastAPI now recommends `pwdlib` + `PyJWT`, not passlib/python-jose).
- **Branches:** Git Flow. `main` (releases, tagged `vX.Y.Z`), `develop` (integration),
  `feature/<name>` — **one branch per feature, not per change**. Small fixes: `fix/<name>`.
  Branch from `develop`, merge back via a Pull Request into `develop`.
- **Commits:** at least one commit per fix/change, but no micro-commits. Conventional
  Commits: `feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`, `docs: ...`,
  `chore: ...`, `build: ...`, `refactor: ...`.
- Ask before decisions that are hard to undo (schema changes to existing data, deleting
  branches, force-push).
- UI and API error messages in **Ukrainian**; code, comments, logs in **English**.

## Stack

| Part | Tech |
|---|---|
| Backend | Python 3.12 (3.10+ compatible: use `timezone.utc`, not `datetime.UTC`), FastAPI, SQLAlchemy 2.0 **sync**, Alembic, psycopg 3, Pydantic v2 |
| Auth | PyJWT (HS256) + pwdlib Argon2id; OAuth2 password flow |
| DB | PostgreSQL 16, local install on Windows (pgAdmin). Docker is optional (ТЗ promises a compose file — `feature/docker`) |
| Payments | Stripe **test mode** (Checkout + webhooks, Stripe CLI), behind an interface with a mock fallback |
| Frontend | React + TypeScript + Vite + Tailwind + **react-i18next from day one** (only `uk.json` now; `en.json` later) |
| Tests | pytest; API tests via FastAPI `TestClient` |

Owner's machine: **Windows**, VS Code, conda env `tour` (Python 3.12), pip.

## Commands (run from `backend/`)

```bash
pip install -r requirements.txt
alembic upgrade head                  # apply migrations to DATABASE_URL
alembic revision --autogenerate -m "..."   # after changing models; review the file!
alembic check                         # models and DB must match
pytest -q                             # uses TEST_DATABASE_URL (wiped every run)
uvicorn app.main:app --reload         # http://127.0.0.1:8000/docs
python -m scripts.create_user --role admin --phone +380500000001 --email admin@tour.local --password "Admin-pass-1" --last-name Адмін --first-name Системний
python -m scripts.generate_er         # regenerate docs/er_diagram.puml from models
python -m scripts.seed_demo           # demo hotels + published tours (needs a manager user)
python -m scripts.expire_orders       # cancel orders whose seat hold ran out (server does it every minute)
```

`backend/.env` (never committed; template in `.env.example`): `DATABASE_URL`,
`TEST_DATABASE_URL`, `SECRET_KEY`, optional `UPLOAD_DIR`/`MAX_IMAGE_MB`/`MAX_IMAGES_PER_TOUR`/`ORDER_EXPIRY_INTERVAL_SEC`, later `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
DB user is **`tour_app`** (owns the databases `tour_website` and `tour_website_test`).

## Architecture

```
backend/app/
  config.py      settings (pydantic-settings, .env)
  db.py          engine, SessionLocal, get_db
  models/        SQLAlchemy models, 27 tables (enums.py = all status codes)
  schemas/       Pydantic request/response models
  routers/       thin HTTP layer: validate -> call service -> commit -> return
  services/      business rules (raise DomainError from services/errors.py; routers map it to HTTPException)
  core/          security.py (hash/JWT), deps.py (DbSession, CurrentUser, require_roles)
backend/alembic/versions/   migrations = source of truth for the schema
backend/tests/              conftest: per-test transaction rolled back; `client`, `manager`,
                            `manager_headers` fixtures; factories.py = data builders;
                            uploads go to a temp dir
backend/uploads/            uploaded files (gitignored); only uploads/tours is public, at /uploads/tours
database/                   SQL exports of migrations for running in pgAdmin
docs/                       ER diagram (generated), ТЗ
```

Conventions:
- Enums are stored as `VARCHAR + CHECK` (`str_enum()` in `models/base.py`), values are
  lower-case English codes; Ukrainian labels live in the frontend.
- Money: `Numeric(12,2)`; rates `Numeric(12,4)`. Order price and `rate_used` are frozen at
  checkout.
- All order status changes go through `services/order_status.py: change_status()` — it holds
  the full ТЗ 4.4.1 transition table, writes `order_status_history` (`changed_by = NULL` means
  the System) and does the quota accounting (-> paid: seats_sold += tourists after re-checking
  free seats; paid states -> rejected/cancelled: seats back). **Never assign `order.status`
  directly.** Who may make a transition is checked by the calling service.
- Seat quota (`services/seats.py`): free seats = `seats_total − seats_sold − seats in unexpired
  holds` (checkout/awaiting_payment with `hold_expires_at > now`); lock the tour row
  (`lock_tour()`, `SELECT ... FOR UPDATE`) when holding/selling seats. The hold lasts
  `booking_timeout_min` (settings, default 20) from order creation and is never extended.
- Expired holds: `services/order_expiry.py: expire_orders()` cancels them as the System; it runs
  every `ORDER_EXPIRY_INTERVAL_SEC` (60; 0 = off, as in tests) from the FastAPI lifespan, and
  via `scripts.expire_orders`. An order touched after its hold ran out is cancelled on the spot.
- Order price (`services/pricing.py`) is Decimal with ROUND_HALF_UP; `total_uah`,
  `discount_uah`, `rate_used` are recalculated only in checkout and at confirm, then frozen.
- Files: only `uploads/tours` (tour photos) is public, mounted at `/uploads/tours`. Never
  mount `upload_dir` itself. Order documents and any personal files (vouchers, tickets,
  passport scans, receipts) are stored **outside** the public folder (e.g.
  `upload_dir/private/...`) and downloaded **only** through an endpoint that checks the user's
  rights (the order's client or staff with the right role). File names on disk are always
  generated by the server, never taken from the client.
- Every new feature ships with tests; `pytest` must be green before a PR.

## Rules for feature/stripe-payments

Decided in advance (no code yet):
- Stripe Checkout Session `expires_at` must be 30 min–24 h after creation, but our hold is
  `booking_timeout_min` (20). So when `expire_orders` cancels an `awaiting_payment` order that
  has a Stripe session, it must expire that session via the Stripe API
  (`POST /v1/checkout/sessions/{id}/expire`), otherwise the client could still pay.
- If a successful payment still arrives for an order that is already cancelled (race at the
  deadline), refund it automatically and do not change the order status.
- Moving to `paid` must re-check free seats under the tour row lock; `seats_sold` must never
  exceed `seats_total` (`change_status()` already does this and raises 409 if seats are gone —
  that case must also lead to an automatic refund).

## Domain cheat-sheet

Roles: `client`, `manager`, `finance`, `admin` (ТЗ 4.3). Staff are created by the admin /
`scripts.create_user`, never self-registered.

Order statuses (ТЗ 4.4.1): `checkout → awaiting_payment → paid → in_progress → confirmed →
documents_ready → completed → archived`; `in_progress → rejected` (full refund);
`paid..documents_ready → cancel_requested → cancelled` (refund minus ФПВ);
`checkout/awaiting_payment → cancelled` on timeout (`booking_timeout_min`, default 20).
Payment status (separate field): `awaiting, partially_paid, paid, partially_refunded, refunded`.
Tour status: `draft ↔ active → archived`.

Price (form 4.6.1.2, field 8): `(base_price × adults + child_price × children) × rate +
insurance × tourists + transfer − promo discount`, child = under 12 at tour start,
`child_price NULL` = base price.

## Status and backlog

Done: `feature/project-skeleton` (models, migrations, reference data, schema tests) →
merged to `develop`, released as `v0.1.0` on `main`. `feature/auth` (register, login by
phone or e-mail, `/me`, password change, `require_roles`, create_user CLI) → merged to
`develop` (PR #1). `fix/tests-read-env` (pytest reads `TEST_DATABASE_URL` from
`backend/.env`, README points to the ТЗ) → merged to `develop` (PR #2, #3).
`fix(db)` script `database/04_fix_owner_to_tour_app.sql` on `develop`.
`feature/tours-catalog` (manager CRUD, copy, statuses + audit_log, photos; public catalog
with filters/sort/pagination, tour page, reference lists; `scripts.seed_demo`) → merged to
`develop` (PR #4). `fix/private-uploads` (only `uploads/tours` is public) → merged (PR #5).

`feature/orders-checkout` (quote, create with seat hold, edit, confirm with offer consent and
frozen price, cancel, my orders with history, saved passports, insurance/transfer lists,
status service, hold expiry loop + CLI; migration `order_number_seq` + `orders.offer_accepted_at`)
— **ready, PR to `develop` pending**.

Backlog, in order (one branch each):
1. `feature/tours-catalog` — **done** (PR #4)
2. `feature/orders-checkout` — checkout, price calc, seat hold + timeout, status service (4.5.3, 4.4.1)
3. `feature/stripe-payments` — Stripe Checkout + webhook, mock gateway, bank transfer confirm (4.5.3, 4.5.6)
4. `feature/order-processing` — manager takes/confirms/rejects, PNR, document upload, cancel + refunds (4.5.4–4.5.6)
5. `feature/reviews` — reviews + moderation + hotel rating (4.5.7)
6. `feature/admin` — users/roles, reference data, rates, settings, promo codes (4.5.8, 4.6.2.3, 4.6.4.1)
7. `feature/frontend-public` — catalog, tour page, auth, checkout, personal account
8. `feature/frontend-backoffice` — manager, finance, admin pages
9. `feature/favorites-history` 10. `feature/notifications-email` 11. `feature/reports` (Excel/PDF)
12. `feature/loyalty` 13. `feature/i18n-en` 14. `feature/monitoring` 15. `feature/docker`

When a feature is merged: tick it in `README.md` "Етапи", update this section, and if a
ТЗ 2.7 "out of MVP" item got implemented, note it for the ТЗ update.
