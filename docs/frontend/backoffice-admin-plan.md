# Plan: back office, administration (spec 13)

Branch `feature/backoffice-admin` (worktree, from `origin/develop`). Spec:
`docs/frontend/13-office-admin.md`. Status: **approved** (answers and additions in §8).

Plain antd, not ProComponents (CLAUDE.md "UI library"): ProTable → `Table` + `FilterBar`,
ModalForm → `FormModal`, DrawerForm → `Drawer` + `Form`, ProForm/ProCard → `Form` + `Card`,
ProDescriptions → `Descriptions`.

## 0. What the backend has today (read from the code)

| Area | Endpoints | What is missing for the spec |
|---|---|---|
| Users (`routers/admin_users.py`, `services/admin_users.py`) | `GET /admin/users?role&is_active&q&page`, `GET /{id}`, `POST` (staff only, **initial password**, no invitations), `PATCH` (role, is_active, names, e-mail, phone; clients too), `POST /{id}/reset-password` | **No per-user actions**: the refusals exist only inside `update_user()`. **Blocking does not cut tokens**: a blocked user is refused on every request and at login (`is_active`), but after unblocking, tokens issued before the block work again (up to 60 min). Reset does cut them (`tokens_valid_after`). `role` filter takes one role, so the «Персонал» tab needs a staff filter. No last login, no block reason (both would need columns). |
| Reference data (`routers/admin_reference.py`, `services/reference_admin.py`) | `/admin/{countries,cities,resorts,hotels,insurance-types,transfer-types}`: list (`?archived`, `?parent_id`), create, patch, archive, restore, delete; `/admin/languages[/{code}]` | **No per-record actions/reasons.** Archiving is refused **only** for the default insurance/transfer — **not** when published tours use the record (spec §2 expects that). Restore is refused under an archived parent; delete when anything refers to it (technical text «tours.hotel_id (3)»). Hotels already have all catalog-improvements fields; `rating_avg` read-only. |
| Settings (`routers/admin_settings.py`) | `GET/PUT /admin/settings` (partial PUT), `GET /admin/payment-gateway` | `changes.updated_by` is an id only; ranges live only in `SETTING_FIELDS`. Not in the API: review photo count (`MAX_REVIEW_PHOTOS` in `.env`), contact address, maintenance message (fixed text in `maintenance.py`). Currency rates (EUR, USD) are **here**, not in the reference data. |
| Maintenance (`services/maintenance.py`) | `maintenance_mode` | Only the admin keeps working; **managers and finance get 503 too**. Webhooks, System jobs and tour photos keep running. |
| Audit (`services/audit.py`) | `GET /admin/audit-log?user_id&entity&entity_id&action&date_from&date_to&page` (Kyiv days) | No author name/role. No IP and no "result" (only successful changes are written). **No export endpoint.** |
| System logs, load report (spec §5) | **none** | Not in the backend (closest: backlog `feature/monitoring`, `feature/reports`). **No pages are made**, as §5 says. |

### Editor lists and archived records (coordination with spec 10)

Checked: `/api/reference/{countries,resorts,hotels,cities,insurance-types,transfer-types}`
(`services/reference.py`) **already exclude archived records**, and also the resorts, hotels and
cities of an archived country and the hotels of an archived resort. The tour service refuses them
on save too (`services/tours.py: _check_hotel` / `_check_city`); orders refuse archived
insurance/transfer. **This branch does not touch `/api/reference/*`**; every change is additive
on `/api/admin/*`, which the tour editor does not use.

Gap: the catalog (`services/catalog.py`) does not look at `is_archived`. Today archiving a hotel or
country used by a **published** tour leaves the tour for sale. Spec §2 settles it: archiving such
a record is **refused** with the server's reason (§1.3), so the catalog needs no change. Old
orders read the tour row and its hotel/resort/country through foreign keys, which archiving does
not touch (criterion §8.3 gets a test).

## 1. Backend changes (no migration)

**No migration is needed.** Everything is computed on read; `users.tokens_valid_after` exists;
the new settings keys (Q2) are rows of the key → JSON `settings` table.

1. **User actions** (`services/admin_actions.py`, the `staff_actions` pattern, spec §0 "show the
   rules, not only an error"): `AdminUserOut.user_actions: [{action, allowed, reason}]`,
   `action ∈ edit | change_role | block | unblock | reset_password`. Refusal functions extracted
   from `update_user()`, called by both the endpoint and the list (one rule, one text):
   - `role_refusal`: a client («Роль клієнта не змінюється…»), yourself, the last active admin;
   - `block_refusal`: yourself, the last active admin; `block` only when active, `unblock` only
     when blocked;
   - `edit_refusal`: a client — «Клієнт змінює свої дані сам у профілі» (spec §1; today the
     backend allows it, so `PATCH` starts refusing names/e-mail/phone for clients — Q3);
   - `reset_refusal`: yourself — «Змініть власний пароль у профілі» (a self-reset ends your own
     session; Q3).
   The list counts active admins once per request (no N+1).
2. **Blocking ends sessions** (spec §1, §8.2): block also sets `tokens_valid_after`, so
   unblocking never revives old tokens; the audit row gets `sessions_ended_at` like the reset.
3. **Archive refusal for published tours**: `archive_refusal` refuses a hotel, resort, country or
   departure city used by a tour with `status = active` — «Використовується в 2 опублікованих
   турах — спершу зніміть їх з продажу». Drafts don't block it (they can't be published with an
   archived hotel anyway).
4. **Reference record actions**: every `*AdminOut` and `LanguageOut` gets `admin_actions`
   (`edit | archive | restore | delete | make_default`) from `archive_refusal`, `restore_refusal`,
   `delete_refusal`, `default_refusal`. Counts are grouped once per list. The delete text becomes
   readable: «Готель використовується (тури: 3, відгуки: 1) — архівуйте замість видалення» (a
   table → Ukrainian label map; the test that checks `tours.hotel_id` is updated).
5. **Users list**: `GET /admin/users?staff=true` (manager + finance + admin) for the «Персонал» tab.
6. **Settings**: `SettingsOut.rules: {key: {min, max, places}}` from `SETTING_FIELDS`;
   `changes[key].updated_by_name`; `limits: {max_review_photos, max_review_photo_mb}` read-only
   from `.env` (shown, not edited). Plus Q2.
7. **Audit**: `AuditLogOut.user_name`, `user_role` (outer join; `null` = Система). Hardening: the
   direct `AuditLog(...)` writes in `cancellation.py`, `order_processing.py` and
   `payments/service.py` go through `audit()` (`tours.py` is left to spec 10, which rewrites it), so `clean()` filters them too (what is
   written today does not change).
8. Tests: every refusal (endpoint and action list agree), block cut-off and login refused, archive
   refused with a published tour, archived country hidden from `/reference/countries` while an old
   order still opens, readable delete text, settings rules, audit author, and a scan test: after
   create staff + reset + block, no audit row holds an Argon2 hash or the password.

## 2. Security check of the audit log (spec §4)

- **Code:** every writer was read. Nothing writes passwords, hashes, tokens, keys or passport
  data: user rows carry role, names, e-mail, phone, is_active; a reset writes only
  `sessions_ended_at`; settings never contain keys (they stay in `.env`); `clean()` drops any field
  named like password/secret/key/token/hash. Phone and e-mail are there by design (ТЗ 5.9),
  admin-only.
- **Dev database:** 478 rows scanned read-only for Argon2 hashes, JWTs, `sk_`/`rk_`/`whsec_`,
  passport/document_number and passport-shaped numbers: **no hits**. Caveat: the dev log holds only
  seed data (no user or settings rows yet).
- **No security problem found.** Weakness: direct writes bypass `clean()` (§1.7 fixes it).

## 3. Frontend (`pages/office/admin/`)

Shared: `api/admin.ts` (hooks, `adminKeys`), types from `npm run gen:api`. Actions use
**`useOfficeAction` unchanged**: without `orderId` it still gives the lock, `busy` and `error`; the
action closure invalidates `adminKeys.*`, and on 409 the page refetches itself. Buttons only from
`user_actions` / `admin_actions` (refused = disabled + server reason as the tooltip/description).
`menu.ts`: the four sections `built: true`; the audit path becomes `audit-log` (spec §4).

1. **`/office/users`** (spec §1) — `Tabs` «Персонал» / «Клієнти» in `?tab=`; `Table`: ПІБ,
   телефон, e-mail, роль `Tag`, статус, дата реєстрації (`created_at`); no last login (not in the
   API). Server pagination; `FilterBar`: `q`, role (staff tab), status. «Додати співробітника»
   (`FormModal`: contacts, role, **temporary password** with `PasswordRules`; the text says the
   employee changes it in the profile). Row → `Drawer` with `Descriptions` and actions:
   - «Змінити роль» (FormModal, staff roles; "access rights change at once");
   - «Заблокувати» / «Розблокувати» (confirm; "all open sessions end"; no reason field — the
     backend has nowhere to store it);
   - «Скинути пароль» (FormModal with the new password; "old tokens stop working");
   - «Редагувати» (staff only).
   Field errors through `mapFormError()` (spec 03 §2a); plain 409 texts in an Alert.
2. **`/office/references`** (spec §2) — `Tabs` in `?tab=`: країни, курорти, міста вильоту,
   готелі, страхування, трансфер. Currency rates and languages live in settings (that's where the
   API has them). Each a `Table` (admin lists aren't paginated → client pagination); `FilterBar`:
   name, «Показати архівні» switch, parent (resort → country; hotel → country, then resort).
   Create/edit: `FormModal`; hotels in a `Drawer` + `Form` with every field (amenities / room types
   as `Form.List`, ≤ 20 × 200 as `text_lists.py`), country → resort dependent selects (resort reset
   when the country changes; only non-archived parents offered), `rating_avg` read-only.
   «В архів» (confirm: not offered in new tours and filters, stays on old orders) / «Відновити» /
   «Видалити» / «Зробити типовим» from `admin_actions`; a 409 shows the server text and refetches.
3. **`/office/settings`** (spec §3) — `Card` groups, each with its **own save button** (partial
   PUT of that group's fields) and `useUnsavedChanges()` across the page:
   - **Відгуки:** `review_premoderation`; photo count and size read-only (`limits`, from `.env`);
   - **Бронювання й оплата:** EUR, USD rates (UAH = 1), `booking_timeout_min`,
     `bank_transfer_hold_hours`, `acquiring_percent`;
   - **Контакти сайту:** `support_phone`, `support_email` (+ address, Q2), `system_email`;
   - **Мови сайту** (form 4.6.4.1 field 5): small `Table`, `uk` locked with the server's reason;
   - **Платіжний шлюз:** read-only `Descriptions`;
   - **Режим обслуговування:** own Card, `Switch` (+ message, Q2) → `Modal` warning, saved at once.
     The spec's text «Клієнти не зможуть користуватися сайтом. Адміністратори матимуть доступ.» is
     extended with «Менеджери й фінансисти також не зможуть працювати», because that's what the
     backend does.
   Each field: a short description (`Form.Item extra`, `uk.json`), limits from `rules`, «Змінено
   <дата>, <хто>».
4. **Maintenance Alert** in `OfficeLayout`: for the admin, `useAdminSettings()` →
   `maintenance_mode` → a warning `Alert` above every office page with a link to settings. Other
   staff can't work then: their pages show the existing maintenance `Result`.
5. **`/office/audit-log`** (spec §4) — `Table`: час (Kyiv), користувач / «Система», роль, дія
   (`uk.json` labels), об'єкт (type + id; a link where a page exists: user → users drawer, order →
   `/office/orders/:id`, reference → its tab). No IP or result columns (not stored), no export (no
   endpoint). `FilterBar`: period, user (select of staff), action, object type. Row → `Drawer`:
   «поле — було — стало» `Table` over the union of keys (labels from `uk.json`, raw key as
   fallback; Так/Ні, «—», lists joined, ISO times as Kyiv time), changed rows marked; raw JSON in a
   collapsed `Collapse`. Read-only, no actions.

## 4. Tests (in the same commits as the code, spec §6)

- Users: the block button is disabled for yourself with the reason; blocking needs confirmation;
  change role sends `{role}`; last admin refused.
- References: archive needs confirmation; the archived switch changes `?archived`; resort depends
  on the country; a refused archive shows the server text.
- Settings: maintenance needs confirmation, then the office shows the `Alert`; a group saves only
  its fields; unsaved-changes warning.
- Audit: no change buttons; the drawer shows «було / стало».
- Unit tests for the before/after formatter. Backend tests as in §1.8.

## 5. Commits (one branch)

1. `docs: add spec 13 and the admin back-office plan`
2. `feat(admin): user actions with reasons, end sessions on block`
3. `feat(admin): reference record actions, archive refused for published tours`
4. `feat(admin): settings rules and limits, author names in settings and audit log`
5. `refactor(audit): write every audit row through audit()`
6. `feat(backoffice): add users and roles management`
7. `feat(backoffice): add reference data management with archive`
8. `feat(backoffice): add global settings and maintenance mode`
9. `feat(backoffice): add audit log viewer`
10. `docs: admin back office in CLAUDE.md and README`

Before the PR: merge `origin/develop` (on a `package-lock.json` conflict take develop's and run
`npm install`; on `schema.d.ts` / `openapi.json` regenerate with `gen:api`), `pytest -q` (own test
DB from `backend/.env`), `npm test`, `npm run build`, `npm run lint`; check the §8 criteria in the
browser (dev server on port 5174).

## 6. Shared code and conflicts with spec 10

- `FilterBar`: not changed; its text / select / switch / dateRange kinds cover every filter.
- `useOfficeAction`: not changed (§3). When spec 10's generalised version lands, the admin pages
  can switch to it in a follow-up; it would need "keys to refresh" and "put the result in the
  cache".
- Likely small merge conflicts: `menu.ts`, `uk.json`, `lazyPages.tsx`, `router.tsx`, generated
  `schema.d.ts` / `openapi.json`. `OfficeLayout.tsx` gets the Alert.

## 7. Questions

1. §1.2 (blocking also ends sessions through `tokens_valid_after`): OK?
2. Spec §3 asks for a contact **address** and a **maintenance message** for visitors; the API has
   neither. Add `support_address` (to `GET /site/contacts`, footer and `/contacts`) and
   `maintenance_message` (used by the 503 instead of the fixed text) as new settings keys — no
   migration — or leave both out?
3. §1.1: the backend starts refusing to edit a client's personal data (spec §1) and refuses a
   reset of your own password. OK?
4. Seen in passing, not in scope (read from `AuthProvider.tsx`, not reproduced): in maintenance a
   manager who reloads the office is probably treated as a guest (`GET /auth/me` → 503), sent to
   `/login`, logs in and is sent back — a loop. Leave it, or a separate `fix/` branch?

## 8. Approved answers and additions

1. Blocking ends the user's sessions (`tokens_valid_after`): yes.
2. `support_address` and `maintenance_message` as new settings keys, no migration: yes. The
   address goes to `GET /site/contacts`, the footer and `/contacts`; the message replaces the
   fixed 503 text (empty = the default text).
3. Editing a client's personal data and an admin resetting their own password through the admin
   reset are refused (with reasons in `user_actions`): yes.
4. The maintenance login loop: a separate `fix/` branch right after this one, keeping the rule
   (only admins work); staff get a clear «Технічні роботи» message. Added to the CLAUDE.md backlog
   as the next item.

Additions:
- **Publishing** is refused while the tour uses an archived hotel, resort, country or departure
  city, with the server's reason. Already true in `services/tours.py` (`_validate_for_publish` →
  `_check_hotel` / `_check_city`); only the archived hotel had a test. New backend tests cover
  resort, country and city, and that existing orders still show the records. `tours.py` itself is
  not changed (spec 10 rewrites its errors); its archived-city text is «Місто відправлення не
  знайдено», noted for spec 10.
- **Staff password change:** «Змінити пароль» in the office avatar menu, a `Modal` with
  `POST /auth/me/password`, the same rules and the same sign-out as the client profile (spec 08),
  reusing its form if it is shared, unchanged.
- **Temporary password** of a new staff member: generated in the form, shown once after creation
  with a copy button and «Передайте співробітнику безпечним способом; він змінить пароль після
  входу». Never logged or audited; a backend test checks the creation audit row does not hold it.
- CLAUDE.md backlog: last login, block reason, IP, result columns, audit export, system logs, load
  report.
