# Plan: back-office tours (spec 10, `feature/backoffice-tours`)

Status: **approved** (2026-11-25). Based on the real code of `develop` at `48e90ad`.

## Decisions taken at approval

- Departures: **option A**, one date range per tour (section 2). A different price period is a
  copy of the tour; spec §5 now says «a range with at least two start dates».
- Locked fields: `title_uk`, `title_en`, `hotel_id`, `departure_from`, `departure_to`, `nights`,
  `transport_type`, `departure_city_id`, `meal_plan`. Prices stay editable (orders freeze their own
  price at confirm). The lock applies while **either**:
  - the tour has ever had a paid order (`paid` in an order's history), or
  - it has **active bookings**: `checkout` / `awaiting_payment` with an unexpired hold, or a
    partly paid transfer (never cancelled automatically). This lock ends by itself when the holds
    run out or are paid. Reason: «N активних бронювань: дочекайтеся оплати або закінчення утримання».
- **Unpublish** keeps active bookings payable. A `checkout` order of an unpublished (draft) tour
  may still be confirmed and paid (`confirm_order` refuses only archived tours); the locks keep
  what the client pays for unchanged. The confirmation shows the number of active bookings.
- **Archive** cancels the tour's unpaid bookings (`checkout` / `awaiting_payment`) through the
  hold-expiry path: `change_status(cancelled)` as the System with a comment «Тур знято з
  продажу», open Stripe sessions closed, the client notified; a late Stripe payment is refunded by
  the existing webhook rule. Each cancelled order is listed in the tour's audit entry. A partly
  paid transfer is never cancelled automatically, so archive is **refused** while one exists
  (finance completes or refunds it first). The confirmation shows how many bookings will be cancelled.
- Restore archived → draft (audited), copy with a new date range in the body, quota ≥ sold +
  unexpired holds, field errors with `loc`, list filters and columns, rules endpoint.
- **No migration.** `feature/order-snapshot` stays in the backlog; the locks are the interim protection.

**Migration: none.** Everything below fits the current schema. The parallel spec 11 session may
create its own Alembic revision without a head conflict from this branch. (If you pick option B
in section 2, that changes: it needs a migration.)

## 1. What the backend has today

Router `app/routers/manager_tours.py` (manager only), service `app/services/tours.py`:

| Endpoint | Today |
|---|---|
| `GET /manager/tours` | `status`, `q` (title uk/en), paging; sorted by `updated_at desc`. Item: id, status, title_uk, hotel_id, dates, nights, seats_total/sold, base_price, currency, is_featured |
| `POST /manager/tours` | always creates a **draft**; full validation |
| `GET /manager/tours/{id}` | `ManagerTourOut`: every field + program_days + images |
| `PATCH /manager/tours/{id}` | **drafts only** (active → 409 «спершу зніміть тур з публікації»); validated on the merged tour; `program_days` replaces the whole program |
| `POST …/copy` | exists: new draft, «(копія)» suffix, program copied, **photos copied as files**, **dates copied** |
| `POST …/publish` / `unpublish` / `archive` | `change_status()` with audit_log. draft ↔ active, both → archived. **Archived is final** (no restore) |
| `POST …/images`, `DELETE …/images/{id}`, `PUT …/images/order` | drafts only; JPG/PNG by magic bytes; `MAX_IMAGE_MB` (5), `MAX_IMAGES_PER_TOUR` (20) |

### Form 4.6.2.1 against the API

| # | Field | API | Note |
|---|---|---|---|
| 1 | Назва (UKR) | `title_uk` | optional: empty → «Готель, Курорт» (the server fills it); max 200 |
| 2 | Назва (ENG) | `title_en` | required; max 200 |
| 3–4 | Країна, курорт | — | not tour columns, they come from the hotel. The editor's selects only filter the hotel list |
| 5 | Готель | `hotel_id` | archived hotel/resort/country refused |
| 6 | Тип транспорту | `transport_type` air / bus / none | |
| 7 | Місто відправлення | `departure_city_id` | required for air and bus |
| 8–9 | Рейси | `flight_out`, `flight_back` | air only; `QU 4433` format, upper-cased by the server |
| 10 | Дати заїздів | `departure_from`, `departure_to` | **one range** (from = to is a single date) |
| 11 | Ночей | `nights` | 1–30 |
| 12 | Жорсткий блок | `seats_total` (+ read-only `seats_sold`) | ≥ 1, ≥ seats sold |
| 13–14 | Ціни | `base_price` (> 0), `child_price` (≥ 0, null = adult price) | Decimal; output is a string, input `number \| string` |
| 15 | Валюта | `currency` UAH / EUR / USD | |
| 16 | Детальний опис | `description` | max 5000, plain text |
| 17 | Програма | `program_days[{day_number, description}]` | 1..N without gaps, at most nights + 1 days, each day max 2000 |
| 18 | Фото | images endpoints | |
| 19 | Рекомендований | `is_featured` | «Гарячі пропозиції» |
| 20 | Статус публікації | status endpoints | buttons, not a checkbox |
| 21 | Харчування | `meal_plan` ro…uai, nullable | |
| 22–23 | Включено / не включено | `included`, `excluded` | `text_lists.py`: ≤ 20 items × 200 chars, trimmed, duplicates dropped |

**Not in the API:** spec's «короткий опис» (there is only one description; I will not add a
column for it) and a per-day title in the program (ТЗ 17.1–17.2 has only number + text). The
editor shows only fields the API accepts, as the spec says.

**Statuses:** the backend has three: `draft` «Чернетка», `active` «Опублікований», `archived`
«Архів». The spec's fourth, «Знятий з публікації», is not stored (unpublish = back to draft, as
ТЗ 4.4.1 says). I show three labels; no migration for a fourth.

## 2. Departures — the main decision for you

The spec asks for a `Form.List` of departures, each with its own date, nights, prices and quota.
**The data model (and ТЗ form 4.6.2.1, field 10) has one date range per tour** with one nights
value, one price pair and one quota. An order stores its own `start_date`/`end_date` (any start
date inside the range, from tomorrow); quota, seats and price live on the tour row.

- **A (recommended):** keep the model. Step 3 is one block: date range (RangePicker; a single
  date is allowed), nights, adult/child price, currency, quota. A second departure with other
  prices or quota = a copy of the tour. The criterion «тур з двома виїздами» becomes «a range
  covering at least two start dates». No migration; matches the ТЗ.
- **B:** a new `tour_departures` table (date, nights, prices, quota, seats_sold) with a migration,
  and orders, seats, pricing, catalog filters/sort, the tour page date picker, the seed and about
  100 tests moved to it. That is a separate feature, larger than spec 10, and the migration would
  collide with the spec 11 session.

## 3. Backend changes (no migration)

### 3.1 `tour_actions` and `locked_fields` (new `services/tour_actions.py`)

Same pattern as `staff_actions.py`: every action is listed only in the statuses its endpoint
accepts; `allowed`/`reason` come from the same refusal functions the endpoints raise with.
New enum `TourAction` in `models/enums.py` (a Python enum only — no DB column, so no migration).

| action | listed in | refused by |
|---|---|---|
| `edit` (PATCH, photos) | draft, active | active: «Спершу зніміть тур з публікації» (ТЗ 4.4.1: an active tour goes back to draft for editing) |
| `publish` | draft | `publish_refusal()` = the current `_validate_for_publish` as a function that returns the first message (archived hotel, no start date from tomorrow, missing field, program too long…) |
| `unpublish` | active | — |
| `archive` | draft, active | — (confirm dialog explains: leaves the catalog, existing orders stay) |
| `restore` | archived | — **new transition archived → draft** (spec asks for «Відновити»; publishing again still needs a valid date). Audited like every status change |
| `copy` | every status | — |

Plus `for_sale: bool` (`catalog.is_for_sale()`) for «Переглянути на сайті».

`locked_fields: [{field, reason}]` — the backlog rule. A tour **has paid orders** when any of its
orders has `paid` in `order_status_history` (so a cancelled-and-refunded or archived order still
counts: its client page still reads the live tour). Then these fields are locked with the reason
«На тур уже є оплачені замовлення: їхні сторінки показують ці дані з туру. Для інших умов
створіть копію туру.»:

- the rule you gave: `title_uk`, `title_en`, `hotel_id`, `departure_from`, `departure_to`, `nights`;
- **recommended addition:** `transport_type`, `departure_city_id`, `meal_plan` — the client's
  order page also reads these live (`order_views.py`, the same list as `feature/order-snapshot`).

`update_tour()` refuses a changed locked field with **409** and `loc=["body", field]` (sending
the same value is fine, so the form may PATCH all fields). `ManagerTourOut` and list items carry
`tour_actions`, `locked_fields`, `for_sale`. Tests: `tests/test_tour_actions.py` (each action ×
status, reasons equal the endpoint's refusal text, lock with paid/refunded/only-checkout orders).

### 3.2 Quota

Today `seats_total < seats_sold` is refused. Seats held by unexpired `checkout`/`awaiting_payment`
orders are not counted, so a quota lowered under them would make those payments fail at `paid`
(409 → automatic refund). Change: under `lock_tour()`, refuse `seats_total < seats_sold + held`
with «Квота не може бути меншою за продані й утримані місця (N)». `ManagerTourOut` gets
`seats_held` and `free_seats` (same `free_seats_expr`) so the editor shows the minimum.

### 3.3 Field errors with `loc`

`tours.py` raises `DomainError(..., loc=("body", field))` (program: `("body", "program_days", i,
"description")`), and the manager tours router answers in FastAPI's 422 shape like the orders
router (`type: "tour_rule"`). The editor puts them under the field (spec 03 §2a); messages
without a field (status, publish refusals) stay plain text for an Alert.

### 3.4 List

`GET /manager/tours` gains: `country_id`, `resort_id`, `departure_from`/`departure_to` (tours
whose range overlaps the period), `sort=updated_desc|departure_asc|title_asc` (title with the ICU
collation, as the catalog). Item gains: country/resort/hotel names, `image_url` (first photo),
`nearest_start` (max(from, tomorrow) if ≤ to, else null → «Дати минули»), `free_seats`,
`base_price` + `currency`, `tour_actions`, `for_sale`. `ManagerTourOut` gains `hotel` (id, name,
stars, resort and country ids/names), so an archived hotel still shows in the editor.

### 3.5 Copy

The DB requires dates, and the spec wants a copy without the old dates. So `POST …/copy` takes a
body `{departure_from, departure_to}`: the copy dialog asks for the new range first (from
tomorrow), then the draft is created with the original's content, program and photo files,
title «Копія — …» / «Copy — …» (spec format, cut to 200), `is_featured=false`, `seats_sold=0`,
and the editor opens on it. Test: dates come from the body, never from the source.

### 3.6 Rules endpoint

`GET /manager/tours/rules` (before `/{tour_id}`): photo limits (`max_files`, `max_file_mb`,
`file_types` from settings — reuses `UploadLimitsOut`), title/description/day lengths, nights
range, list limits (`text_lists`), day limit «nights + 1». The frontend reads limits from here;
nothing hard-coded.

Existing behaviour kept, noted for the defence: an unpublished tour stops new bookings at once
(`_bookable_tour`), but an order already in `awaiting_payment` can still be paid by its Stripe
session (the seats were held while the tour was public).

## 4. Frontend

Plain antd, reusing 09: `OfficeLayout`, `features/office/menu.ts` (`tours: built: true`),
`FilterBar`, `urlState.ts`, `FormModal`, `actionErrorText`, `StatusTag` + `orderStatus.ts`.

- **Status dictionary:** `TOUR_STATUS_TONES` + labels in `constants/orderStatus.ts`; the existing
  test against `openapi.json` covers the tour enum too.
- **Actions:** `useOfficeAction` is order-specific (`isOrder`, order keys). I generalise it with
  an options object (result → cache key, what to refresh); the order pages keep their behaviour
  and tests. `features/office/tourActions.ts: findTourAction()`. Buttons only from
  `tour_actions` (allowed = button, refused = disabled + server reason). Archive, unpublish and
  restore ask first (Popconfirm/Modal with consequences); the button is locked while the request runs.

### 4.1 `/office/tours` (`OfficeToursPage`, `officeToursParams.ts`)

Table with server paging/sorting; state in the URL under API names. Columns: thumbnail
(`PhotoPlaceholder` if none), title, country / resort, hotel, nearest start, price from (adult,
tour currency, `formatMoney`), free / total, status tag, actions (Редагувати, Копіювати,
Опублікувати / Зняти, В архів / Відновити, Переглянути на сайті → `/tours/:id` in a new tab only
when `for_sale`). FilterBar: title, country, resort (depends on country), status, departure
period. «Створити тур» button. Horizontal scroll at 768 px.

### 4.2 Editor `/office/tours/new`, `/office/tours/:id/edit` (`pages/office/tours/`)

`Steps` + one antd `Form` (`preserve` on, so going back keeps values), step in `?step=`:

1. **Основне:** title UK (placeholder shows the auto «Готель, Курорт»), title EN, country →
   resort → hotel (changing country clears resort and hotel; changing resort clears hotel),
   transport, departure city (air/bus), flights (air only), meal plan, featured, description,
   included / excluded (`Form.List` of short lines).
2. **Програма:** `Form.List` of days: number shown from the position (1, 2, 3…), text; add,
   remove, up/down (`move`). Numbers are sent from the order at save time.
3. **Дати, ціни, квота:** option A block. Dates from tomorrow (Kyiv), nights 1–30, prices with
   `InputNumber stringMode` (values stay decimal strings, checked by a regex, never `Number()`),
   child price optional, currency, quota ≥ max(1, sold + held) with the numbers shown.
4. **Фото:** antd `Upload` (`beforeUpload` → `fileProblem()` with the rules endpoint limits,
   count checked against the limit), each upload/delete/reorder is an immediate server call;
   grid with «Головне» on the first, «Зробити головним», up/down (no drag: keyboard friendly, no
   animation), delete with Popconfirm. A new tour must exist first: leaving step 3 of a new tour
   saves it as a draft (POST) and the URL becomes `/office/tours/:id/edit?step=photos`.
5. **Перевірка:** `Descriptions` summary of all steps, the publish refusal (if any) as an
   Alert, two buttons: «Зберегти як чернетку» (PATCH) and «Зберегти й опублікувати» (PATCH, then
   POST publish; if publish is refused the draft is saved and the reason is shown).

- Locked fields: `disabled` with the server's reason as help text and a lock icon (`aria-hidden`).
- Active tour: the form is read-only with an Alert from the `edit` reason and «Зняти з
  публікації й редагувати» (confirm: the tour leaves the catalog until published again).
  Archived: read-only, «Відновити» and «Копіювати».
- Validation as spec 03 §2a: `onBlur`, then `onChange` after the first attempt; «Далі» validates
  the step's fields, scrolls and focuses the first error; server 422 `loc` → `form.setFields`
  (switching to that field's step); other errors → Alert. Client rules in
  `features/office/tourRules.ts` mirror `services/tours.py` (same texts; change both together).
- **Unsaved changes:** `useUnsavedChanges(dirty)` = `useBlocker` (Modal «Вийти без
  збереження?») + `beforeunload`. Dirty = the form differs from the last saved tour; photos are
  saved at once, so they never count. The router is `createBrowserRouter`, so `useBlocker` works.
- **Copy:** «Копіювати» (list and editor) opens a `FormModal` with the new date range → POST copy →
  editor of the new draft, step 1.

### 4.3 Tests (Vitest, with the code)

Country → resort → hotel dependency and reset; program add/remove/move renumbering; step 3:
past date, price 0, 0 seats refused; draft vs publish send PATCH vs PATCH + publish; copy sends
the new dates and opens a draft; archive needs confirmation; locked field disabled with reason;
blocker on leaving with changes; list filters in the URL; actions only from `tour_actions`.

## 5. Commits

1. `docs: add spec 10 (office tours) and plan`
2. `feat(tours): add tour actions, locked fields, quota with holds and list filters` (+ tests)
3. `feat(backoffice): add tours list with publish and archive actions`
4. `feat(backoffice): add tour editor with program, dates and photos`
5. `feat(backoffice): add tour copy`
6. `docs: back-office tours status in CLAUDE.md and README`

Then `gen:api`, all checks (`pytest`, `npm test`, `build`, `lint`, `tsc`), manual check of spec §5
against the real backend with the seed manager, merge `origin/develop` (on a `package-lock.json`
conflict take develop's and `npm install`), PR to `develop`.
