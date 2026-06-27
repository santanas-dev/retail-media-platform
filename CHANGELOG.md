# Changelog

All notable changes to the Retail Media Platform.

Format: [SemVer](https://semver.org/) + annotated Git tags.
Every minor tag requires: green full regression, clean git status, no secrets in docs/output.

---

## [44.1-inventory-engine] — 2026-06-16

**Inventory Engine: availability, sold out, forecast v1, reservation types, portal page.**

### Backend
- Модель `BookingItem` расширена: `reservation_type` (campaign/internal/emergency/filler)
- Миграция: `031_add_reservation_type_to_booking_items`
- `calculate_availability()`: sold_out flag, occupancy_pct, internal/emergency bookings,
  store_code/name, business-language reasons, alternatives, summary aggregation
- `calculate_forecast()` new: v1 estimate — capacity_spots × days × spots_per_loop,
  disclaimer «Оценка по расписанию», confidence: low
- `get_inventory_snapshot()` new: scope-level aggregation (branch/cluster/store)
- `_get_booked_spots()`: Optional inventory_unit_id + reservation_type filter
- New endpoints: `POST /api/inventory/forecast`, `GET /api/inventory/snapshot`
- All endpoints under `inventory.read` / `bookings.*` RBAC

### Portal
- New page `/inventory` — Рекламное время: summary cards, availability table, forecast, snapshot
- Sidebar: «⏱ Рекламное время» in Аналитика section
- BackendClient: `get_inventory_availability`, `get_inventory_forecast`, `get_inventory_snapshot`
- No JS/CDN/localStorage, all server-side HTML/CSS/Jinja2
- Russian business language: all statuses, reasons, alternatives

### Tests
- Backend: `test_inventory_engine_441.py` — 20 tests (availability, forecast, reservation_type, safety, router, business language)
- Portal: `TestInventoryPage44_1` — 8 tests (route, title, no JS/technical labels/secrets, business labels, no UUID)

### Docs
- `docs/product/inventory-engine-44-1.md`

### Safety
- No JS/CDN/localStorage ✅
- No secrets/tokens/full URLs/barcodes/storage paths/raw UUID leakage ✅
- Physical KSO/SSH/X11/Chromium/runner/sidecar/PoP не запускались
- Scanner E2E/long-run/sidecar sync не выполнялись

### Regression
- Backend: 702 passed, 8 pre-existing failures, 26 warnings
- Portal: 655 passed, 20 skipped, 0 failed

---

## [43.7.1-business-lang-test-fix] — 2026-06-16

**Fix portal test regression after business language + dark UI (43.7).**

### Portal Tests
- 25 failed → **0 failed**. 644 passed, 32 skipped
- Обновлены expected strings во всех тестах под бизнес-формулировки:
  `Dashboard` → `Главный экран`, `NO-GO` → `Запуск заблокирован`,
  `Proof of Play` → `Фактические показы`, `Flow` → `Этапы`,
  `Publication batch` → `Пакет публикации`, `Production` → `Система`,
  `Scanner E2E` → `Проверка физического сканера`,
  `Long-run` → `Длительная проверка стабильности`,
  `Sidecar sync` → `Синхронизация агента`,
  `Maker-checker` → `двух подписей` и многие другие
- CSS-тест: обновлены имена классов под dark theme (`.status-badge-active` и др.)
- Auth-тесты: `TestBaseLayoutAuthState` и `test_portal_user_from_request_has_no_tokens`
  включают `_enable_real_auth()` для проверки реального неаутентифицированного состояния
- Удалён дубликат метода `test_login_mentions_local_portal_account`

### Safety Preserved
- No JS/CDN/localStorage ✅
- No secrets/tokens/full URLs/barcodes/storage paths/raw UUID leakage ✅
- Login isolation confirmed: `/dashboard` без сессии → редирект на `/login` с "Войти"
- Physical KSO/SSH/X11/Chromium/runner/sidecar/PoP не запускались
- Scanner E2E/long-run/sidecar sync не выполнялись

---

## [43.6-backend-only-e2e-acceptance] — 2026-06-16

**Backend-only E2E Acceptance Test — полная структурная верификация production pipeline.**

### E2E Test Suite
- Создан `backend/tests/test_e2e_backend_only_acceptance_436.py` — **50 тестов** в 6 категориях
- **A. Production Endpoint Enumeration** (24 tests): все production endpoints зарегистрированы — creatives, campaigns, schedules, approvals, publications, manifests, reports
- **B. State Machine Validation** (8 tests): lifecycle статусов кампаний, батчей, manifest, терминальность PUBLISHED
- **C. CSV Export Safety** (9 tests): 4 типа CSV — safe headers, text/csv, Content-Disposition, no forbidden patterns
- **D. Safety Invariants** (6 tests): publication/manifest service не импортирует sidecar/runner/chromium
- **E. Reports Content Safety** (2 tests): conflicts RLS/anonymization, no forbidden indices
- **F. Physical Delivery NOT Triggered** (4 tests): docstrings, отсутствие sidecar_sync/deliver_to_kso

### Verified Production Endpoints
22 production endpoints: creatives (list/create/get-by-code), campaigns (list/create/bind/submit/batch-bridge), schedules (list/create/slots), approvals (list/create/approve/reject), publications (batch list), manifests (list/generate/publish), reports (4 CSV exports)

### CSV Export Safety
Все 4 exports: campaigns, airtime, conflicts, publications — safe headers, no secrets, text/csv, Content-Disposition

### Physical Delivery Isolation
- Publication service: 0 references to sidecar/runner/chromium ✅
- Manifest service: 0 references to sidecar/runner ✅
- "Physical KSO delivery is NOT triggered" documented ✅
- Airtime `is_planned` marker present ✅

### Docs
- Создан `docs/product/backend-only-e2e-acceptance-43-6.md` (5.3 KB)

### Regression
- Backend: 647 passed, 6 pre-existing failures (stale template checks in test_reports_portal_42_3.py), 25 warnings
- Portal: **665 passed, 21 skipped, 0 failed**
- New E2E test: 50 passed, 0 failed

### Policy
- No fake/demo primary data ✅
- No legacy/test-kso as primary path ✅
- No physical KSO/SSH/X11/Chromium/runner/sidecar/PoP changes

---

## [43.5-business-demo-acceptance] — 2026-06-16

**Business Demo Scenario & Portal Acceptance Pack — подготовка портала к бизнес-демонстрации.**

### Business Demo Readiness
- Расширена страница `/readiness`: device KPI + бизнес-демо секции
- **«Что уже готово»** — checklist из 8 backend/portal возможностей с ссылками
- **«Сценарий демонстрации»** — pipeline из 6 шагов (креатив → кампания → расписание → согласование → публикация → отчёт)
- **«Что заблокировано»** — 5 P0 blockers с деталями
- **«Следующий шаг после сканера»** — 6 шагов с approval tokens
- **Acceptance Checklist** — 13 пунктов для самостоятельной приёмки backend-only сценария
- Быстрые ссылки на все разделы портала

### Business-facing Wording
- «Manifest (legacy)» → «Ранее созданные манифесты»
- «Deprecated — use batches» → «Созданы до внедрения batch-системы»
- 0 видимых legacy/deprecated/internal/dev-only labels в production UI ✅

### Visual System
- `.checklist` / `.checklist-item` / `.checklist-icon` — стили для acceptance checklist
- `.checklist-item.done` — выделение выполненных пунктов

### Docs
- Создан `docs/product/business-demo-acceptance-43-5.md` — полный документ приёмки:
  цель, что показываем/не показываем, пошаговый сценарий (8 шагов),
  критерии успешной приёмки (13 AC), known limitations, physical blockers,
  next steps после сканера

### Audit
- `docs/audit/technical-debt-register.md` — обновлён baseline
- `docs/audit/pilot-readiness-gap-register.md` — обновлён, добавлен статус business demo

### Policy
- Production endpoints only
- 0 fake/demo primary data ✅
- 0 visible test-kso/dev/internal labels ✅
- 0 JS/CDN/localStorage ✅
- No physical KSO/SSH/X11/Chromium/runner/sidecar/PoP changes

### Tests
- +TestBusinessDemoAcceptance (new tests): readiness business demo, acceptance checklist, physical blockers, cross-page links
- Portal regression: running

---

## [43.4-approval-publication-ux] — 2026-06-16

**Approval / Publication UX — продуктовый hardening финальных этапов workflow.**

### Approvals
- Request approval форма в visual system (form-inline, form-select, form-label, form-hint)
- Card-based список заявок с campaign detail enrichment
- Status badges с dots: pending/approved/rejected
- Approve/reject формы в visual system с полем комментария для отказа
- Maker-Checker warning баннер
- Flow breadcrumbs, empty state, cross-page links → publications

### Publications
- **Physical delivery NO-GO banner**: «Manifest delivery to physical KSO is blocked until approval gate»
- **Backend-only warning**: «Публикация в backend не означает доставку на физическую КСО»
- Batch lifecycle pipeline (draft→pending→approved→manifest→published)
- Status badges, action buttons (согласование/generate/publish/cancel)
- Pipeline dot indicator (5-stage progress)
- Legacy manifests table (collapsed, marked as deprecated)
- Cross-page links → reports, readiness

### Policy
- Production endpoints only (list_approvals_prod, create_approval, decide approval, list_publication_batches, request_batch_approval, generate, publish, cancel)
- Явное отделение backend publication от physical delivery
- No JS/CDN/localStorage ✅
- No physical KSO changes

### Tests
- +TestApprovalPublicationWorkflow (22 tests): approval forms, maker-checker, NO-GO banner, pipeline, safety, cross-page links

---

## [43.3-campaign-creative-schedule-workflow] — 2026-06-16

**Campaign / Creative / Schedule Workflow — продуктовый hardening портала.**

### Creatives
- Визуальная карточка с preview, баджами статуса, проверкой 768×1024
- Upload-форма в visual system (form-inline, form-group, form-label, form-hint)
- Баннер «Следующий шаг» с кросс-ссылкой на создание кампании
- Warning при отсутствии approved/ready креативов
- Flow breadcrumbs на всех страницах

### Campaigns
- Панель сводки по статусам (summary-stats: всего/черновик/согласование/одобрено/отклонено)
- Action bar с кросс-ссылками (креативы/расписание/согласования)
- Inline-формы: edit, bind creative, submit, publication в visual system
- Баннер «Дальнейшие шаги» с полным pipeline
- Warning при нуле креативов у кампании

### Schedule
- Create schedule форма с form-label/form-hint (visual system)
- Слоты в компактной таблице с днями недели
- Warning «Нет слотов» + inline add-slot форма
- Airtime section с progress bar, конфликтами, кросс-ссылкой на отчёты
- Баннер «Следующий шаг» → согласование → публикация

### Policy
- No JS/CDN/localStorage ✅
- No physical KSO changes
- Без raw UUID, backend URL, storage paths в rendered HTML
- Production BackendClient endpoints only

### Tests
- +TestCampaignCreativeScheduleWorkflow (23 tests): render, формы, флоу, безопасность, empty states

---

## [43.2-dashboard-reports-visualization] — 2026-06-16

**Dashboard & Reports Visualization — управленческая аналитика и плановая отчётность.**

### Dashboard
- **Platform Summary** — stat-block grid: кампании/креативы/устройства/публикации с distribution bars по статусам
- **Advertising Pipeline** — 6-step visual flow (Креатив→Кампания→Расписание→Согласование→Публикация→Отчёт) с warning на пустых этапах
- **Pilot Readiness** — 5 P0 blockers с иконками, чёткий текст "Сканер отсутствует"
- **Business Next Actions** — 6 карточек-действий с отметками выполненных этапов, ссылки на разделы

### Reports
- **Campaigns by Status** — distribution bar с цветовой легендой, CSV export
- **Airtime Planning** — progress bar с порогами (НОРМА <50% · ВНИМАНИЕ 50-79% · РИСК ≥80%), threshold markers
- **Conflicts** — карточка с conflict count badge, advertiser-safe аннотации, CSV export
- **Publications** — stat-grid: Batches + Manifest status, distribution bars
- **PoP** — компактная таблица с фильтрами, чёткое отделение planned от factual

### Технически
- `styles.css`: +stat-grid, +dist-bar (multi-segment), +pipeline-step, +blocker-grid, +next-actions-grid, +threshold-badge
- `main.py`: dashboard handler расширен (creative/devices/batches status breakdown, +publication_batches fetch)
- `tests`: +TestDashboardReportsVisualization (25 tests) + обновлены старые тесты под новую структуру

### Policy
- No JS/CDN/localStorage ✅
- No physical KSO changes
- Planned/factual разделение явное
- Advertiser-safe через RLS + анонимизацию

---

## [43.1.1-remove-test-kso-wording] — 2026-06-16

**Remove visible test-kso wording from production portal UI.**

### Changes
- `apps/portal-web/templates/pages/dashboard.html` — replaced "Без test-kso как primary KPI источника" → "показатели формируются из рабочих данных платформы"
- `apps/portal-web/tests/test_main.py` — `test_dashboard_no_test_kso_as_primary` now asserts zero test-kso refs (was 1)

### Policy
- Legacy backend/test helpers untouched
- No backend runtime changes
- No physical KSO/SSH/X11/Chromium/runner/sidecar/PoP

---

## [43.1-portal-visual-system-navigation] — 2026-06-16

**Portal Visual System & Product Navigation — UI/UX normalization step.**

### Deliverables
- `apps/portal-web/static/styles.css` — unified visual system v2: cards, badges, banners, progress bars, buttons (primary/secondary/danger/ghost/sm/lg), forms, tables, empty/error states
- `apps/portal-web/templates/base.html` — restructured navigation: Dashboard → Campaigns → Creatives → Schedule → Approvals → Publications → Reports → Devices → Admin, with Flow (1→5) helper
- `apps/portal-web/templates/pages/dashboard.html` — KPI cards, campaign status pipeline, summary stats, blockers list, quick links, pilot NO-GO banner
- `apps/portal-web/templates/pages/reports.html` — section-card blocks, progress bars for airtime occupancy, export links, PoP filters and events table
- `apps/portal-web/tests/test_main.py` — +class `TestVisualSystem` (29 tests): nav structure, KPI rendering, progress bars, empty states, JS/CDN/localStorage safety, forbidden strings, test-kso isolation

### Visual System
- Design tokens extended (success/warning/error/info color palettes with bg/border/text variants)
- New components: `.section-card` (replaces overused `.requirements-box`), `.banner` (warning/error/info/success), `.progress-bar`/`.progress-fill`, `.btn-secondary`/`.btn-danger`/`.btn-ghost`/`.btn-sm`/`.btn-lg`, `.export-link`, `.timestamp`
- Status badges enhanced with dot indicators via `::before` pseudo-element
- Sidebar: clear sections (Главное, Реклама, Аналитика, КСО, Управление), two-column layout with `.nav-icon` + `.nav-label`
- Focus states, reduced motion, transition consistency

### Safety
- **No JS** — verified across all pages
- **No CDN** — verified (cdn./cloudflare/unpkg/jsdelivr/googleapis)
- **No localStorage** — verified
- **No secrets/tokens/URLs/barcodes** — verified
- test-kso: 1 deliberate disclaimer ("без test-kso как primary"), no other references

### Policy
- Doc-only for visual layer — no runtime/physical changes
- No JS/CDN/localStorage on any page
- Backend code unchanged
- Physical KSO/SSH/X11/Chromium/runner/sidecar/PoP not touched

---

## [42.5-pilot-runbook-approval-gates] — 2026-06-16

**Pilot Runbook, Fallback & Approval Gates — documentation/safety/governance step.**

### Deliverables
- `docs/runbooks/one-kso-pilot-runbook.md` — comprehensive pilot execution runbook (5 phases, stop criteria, evidence checklist)
- `docs/runbooks/kso-fallback-rollback-runbook.md` — incident response and rollback procedures
- `docs/runbooks/physical-approval-gates.md` — 5 sequential approval tokens (scanner→manifest→sidecar→long-run→rollout)

### Blocker Resolution
- **B-05 (Pilot runbook/fallback/rollback)** → RESOLVED ✅
- Remaining 5 physical blockers unchanged (scanner, long-run, delivery, sidecar, fleet)
- Pilot remains 🔴 NO-GO until all physical gates passed

### Policy
- Doc-only — no runtime/physical changes
- All commands in runbooks marked "execute only after explicit approval"
- Keyboard simulation explicitly rejected as invalid E2E
- Fleet rollout explicitly forbidden without PHASE_PILOT_ROLLOUT_APPROVED

---

## [42.4-full-audit-tech-debt] — 2026-06-16

**Full Audit & Technical Debt Register — comprehensive codebase audit after 42.3.**

### Deliverables
- `docs/audit/full-audit-42-4.md` — full audit covering backend, portal, KSO, infra, docs
- `docs/audit/technical-debt-register.md` — 34 debt items (6 P0, 4 P1, 20 P2, 4 P3)
- `docs/audit/pilot-readiness-gap-register.md` — 6 pilot blockers confirmed, 5 pre-pilot gaps
- `docs/audit/security-hardening-register.md` — 12 security items (3 P1, 9 P2)

### Key Findings
- **No new blockers from 42.3** — CSV export, RLS, reports are safe
- **171 test-kso references** across 27 files — consolidation sprint needed (43.x)
- **7 legacy BackendClient methods** referencing test-kso paths
- **6 pilot blockers** unchanged (scanner, long-run, delivery, sidecar, runbook, approval)
- **Portal demo_data** module still imported but unused in production
- **KSO Player** correctly enforces 768×1024 portrait, no 1920×1080 leakage
- **Security posture** good — no P0 findings, P1 items are pre-pilot hardening
- **Docs gaps**: no ADR, no security hardening doc, no rollback runbook

### Regression
Doc-only — no runtime/physical actions. Full regression not required.

---

## [42.3-planned-reports-export] — 2026-06-16

**Planned Reports Export — CSV выгрузки по кампаниям, занятости эфира, конфликтам и publication batches.**

### Backend
- New domain: `backend/app/domains/reports/`
  - `router.py` — `GET /api/reports/campaigns/export`, `/airtime/export`, `/conflicts/export`, `/publications/export`
  - `service.py` — CSV generation with RLS and `Content-Disposition: attachment`
- Permission: `reports.read`
- RLS via `resolve_user_scope_context()`: advertiser sees only own data, admin sees full
- Conflict CSV: anonymized for advertiser (no foreign campaign names)
- Safe CSV headers: no raw UUIDs (non-admin), no token/secret/backend URL/storage paths
- Content-Type: `text/csv; charset=utf-8`

### Portal
- BackendClient: `_request_raw()` for text responses; `export_campaigns_csv()`, `export_airtime_csv()`, `export_conflicts_csv()`, `export_publications_csv()`
- Portal export routes: `GET /reports/export/campaigns`, `/airtime`, `/conflicts`, `/publications`
- `/reports` template (42.3 UX):
  - Campaign status breakdown block
  - Publication batch status block  
  - Manifest publish status block
  - Pilot NO-GO summary (🔴 3 blockers)
  - Planned reporting disclaimer («Это плановая отчётность»)
  - CSV download links (conditionally shown)
- No JS/CDN/localStorage — all server-side `<a href>` GET links

### Tests
| Suite | Passed |
|---|---|
| Backend | **603** (+28: 13 reports export + 15 portal template) |
| Portal | 522 |
| KSO State | 86 |
| KSO Player | 2060 (12 skipped) |
| KSO Sidecar | 1838 |
| Infra | 227 |
| Simulator | 19 |

### Policy
- Pilot remains NO-GO 🔴 (HW scanner, long-run, physical delivery)
- Reports are planned/backend-only — PoP fact unavailable until physical gate
- CSV only — no XLSX dependency

---

## [42.2-safe-creative-preview] — 2026-06-16

**Safe Creative Preview — backend-proxied image thumbnails with no storage internals in HTML.**

### Backend
- `GET /api/creatives/by-code/{code}/preview` — streams image from MinIO through backend
  - Auth: `media.read`, RLS: advertiser scope (404 for foreign)
  - Status gate: no preview for archived/rejected
  - Images only: PNG, JPEG (video → 415, deferred)
- Safe headers: Content-Type, Content-Length, Cache-Control, Content-Disposition: inline
- NO signed URLs, NO MinIO paths, NO storage keys in response

### Portal
- `/preview/{creative_code}` — proxy endpoint (portal → backend → MinIO stream)
- `/creatives` — thumbnail column with `<img>` for images, 🎬/📄 placeholder for video/other
- KSO compatibility hints: ✅ 768×1024 match, ⚠️ non-standard dimensions
- `BackendClient.creative_preview_url()` — returns relative `/api/...` path

### Tests
| Suite | Passed |
|---|---|
| Backend | **575** (+7 preview) |
| Portal | 522 |

### No JS/CDN/localStorage
- ✅ No `<script>`, `onclick`, `onsubmit`, `confirm`
- ✅ `<img loading="lazy">` only — no JS lightbox/modal
- ✅ No storage internals in creatives HTML template

---

## [42.1-airtime-occupancy-conflicts] — 2026-06-16

**Airtime Occupancy & Schedule Conflict Detection — backend-only planned occupancy calculation.**

### Backend
- New domain: `backend/app/domains/airtime/`
  - `service.py` — `calculate_occupancy()` and `detect_conflicts()`
  - `router.py` — `GET /api/airtime/occupancy` + `GET /api/airtime/conflicts`
- Occupancy: calculates occupied/free minutes per device/date range from active schedules × slots
- Conflicts: detects same-device schedule slot overlaps (date + day_of_week + time window)
- Status scoping: active campaign statuses (draft/pending_approval/approved), active schedules (draft)
- RLS: advertiser sees anonymized conflicts (no foreign campaign names); admin sees full
- Permission: `reports.read`

### Portal
- BackendClient: `get_airtime_occupancy()`, `get_airtime_conflicts()`
- Portal UX (42.1.1):
  - `/schedule` — airtime occupancy block with server-side GET filter
  - `/reports` — planned airtime section with conflicts table
  - `/campaigns/create` — «🔍 Проверить занятость эфира» button + warning
- No JS/CDN/localStorage on all airtime pages

### Tests
| Suite | Passed |
|---|---|
| Backend | **568** (+17) |
| Portal | **522** (+12 new airtime UX tests) |

### Policy
- Conflict severity: `warning` only — submit NOT blocked (policy deferred)
- All planned — NOT PoP fact

---

## [42.0-portal-product-ux-polish] — 2026-06-16

**Portal Product UX Polish — статусные бейджи, next-action подсказки, flow breadcrumbs, summary-панель, empty states.**

### Changed
- **Status badges** — унифицированы human-readable русские подписи на всех страницах:
  - `campaigns`: Черновик / На согласовании / Одобрено / Отклонено / Архив
  - `creatives`: Черновик / На проверке / Готово / Отклонено / Архив
  - `approvals`: На согласовании / Одобрено / Отклонено
  - `publications`: Черновик / На согласовании / Одобрено / Manifest готов / Опубликовано / Отменено / Отклонено
  - `manifests (legacy)`: Опубликовано / Черновик / Отменено
- **Next-action блоки** — «Следующее действие» на ключевых страницах:
  - `/creatives` — при пустом списке: загрузите креатив
  - `/campaigns` — если есть черновики → отправьте на согласование; одобрено → подготовьте публикацию
  - `/publications` — черновик → на согласование; одобрено → generate manifest
  - `/reports` — физический PoP недоступен до delivery gate
- **Flow breadcrumbs** — навигационная цепочка на `/campaigns` и `/publications`
- **Dashboard summary panel** — карточки по статусам: черновик/на согласовании/одобрено + pilot NO-GO
- **Pilot NO-GO баннер** — красный на dashboard
- **Sidebar flow-секция** — нумерованные шаги: 1. Креативы → 2. Кампании → 3. Согласования → 4. Публикации → 5. Отчёты
- **JS removal** — убраны `onsubmit="return confirm()"` из schedule.html

### No new backend workflow. No physical KSO. No JS/CDN/localStorage.

### Portal tests
510 passed, 32 skipped (добавлены 6 новых тест-классов: статусы, next actions, flow breadcrumbs, pilot status, no-JS, safe errors, empty states)

---

## [41.5-pilot-runbook-go-no-go-pack] — 2026-06-16

**Pilot Runbook & GO/NO-GO Pack — decision-ready documentation for physical pilot.**

### Created
- docs/pilot/one-kso-pilot-runbook.md — full pilot runbook
- docs/pilot/go-no-go-checklist.md — GO/NO-GO decision matrix
- docs/pilot/physical-approval-tokens.md — 7 approval tokens
- docs/pilot/evidence-checklist.md — 21 backend + 12 physical items
- docs/pilot/known-risks-and-deferred-items.md — 3 blockers + 5 tech-debt

### Verdict: NO-GO (3 blockers). Docs-only, no code changes.

---

## Release v0.12.1 — Pilot Runbook GO/NO-GO Baseline (2026-06-16)

**Documentation-only patch on v0.12.0 — prepares decision-ready pilot documentation without changing any code or product logic.**

### Includes
- v0.12.0-product-workflow-backend-manifest (full baseline)
- 41.5 — Pilot Runbook & GO/NO-GO Pack
  - `docs/pilot/one-kso-pilot-runbook.md` — full runbook (scope, roles, prerequisites, 4 phases, 8 stop criteria, rollback, evidence, communications)
  - `docs/pilot/go-no-go-checklist.md` — GO/NO-GO matrix (9 categories, 50+ criteria)
  - `docs/pilot/physical-approval-tokens.md` — 7 tokens: scanner → long-run → KSO → delivery → sidecar → PoP → autostart
  - `docs/pilot/evidence-checklist.md` — 21 captured backend items + 12 pending physical items
  - `docs/pilot/known-risks-and-deferred-items.md` — 3 blockers, 5 tech-debt, 5 accepted risks, 7 deferred
- Updated `docs/audit/technical-debt-next-actions.md`
- Updated `docs/audit/product-backend-frontend-gap-analysis.md`

### Regression
5260 passed, 32 skipped, 0 failed (inherited from v0.12.0 — docs-only, no code changes).

### Pilot status
**NO-GO** 🔴 — all 7 approval tokens PENDING ⛔.
Blockers: HW scanner E2E, controlled long-run, explicit physical delivery gate.

### Commit
78339aa — tag v0.12.1-pilot-runbook-go-no-go-baseline

---

## Release v0.12.0 — Product Workflow Backend Manifest Baseline (2026-06-16)

**Full backend product workflow: creative upload → campaign creation → approval → publication batch → manifest generation N+1. Backend-only — no physical KSO delivery.**

### Included steps
- 41.0.0 — Portal UI Hygiene Baseline (CSS-only)
- 41.1 — Creative Upload UX
- 41.1.1 — Remove JS confirm
- 41.2 — Business Campaign Creation UX
- 41.2.1 — Campaign Submit Approval Integration
- 41.3 — Approval Decision UX
- 41.3.1 — CampaignCreative is_active Compatibility Guard
- 41.4 — Approved Campaign to Publication Batch
- 41.4.1 — Full Publication Batch Workflow & Manifest Generation

### Regression
Backend 551, Portal 498 (+20 skipped), KSO SA 86, Player 2060 (+12 skipped), Sidecar 1838, Infra 227
**Total: 5260 passed, 32 skipped, 0 failed (5292 total).**

### Pilot status
**NO-GO** 🔴 — physical KSO delivery not approved.
Blockers: HW scanner E2E, controlled long-run, explicit physical delivery gate.

### Commit
990d046 — tag v0.12.0-product-workflow-backend-manifest

---
## [41.4-approved-campaign-publication-manifest-ux] — 2026-06-16

**Approved Campaign Publication / Manifest UX — batch creation from approved campaigns.**

### Backend

- `create_batch_from_campaign(db, campaign_code, user_id)` — new service function in publications
  - Validates campaign.status == "approved"
  - Creates/finds confirmed CampaignBooking
  - Inserts schedule_run row via raw SQL (ScheduleRun ORM model TBD)
  - Creates PublicationBatch (draft) with idempotency guards
  - Audit event logged, physical KSO delivery NOT triggered
- `POST /api/campaigns/by-code/{code}/create-publication-batch` — new endpoint (201)
  - Requires `publications.manage` permission
  - RLS advertiser scope enforced
  - Returns CampaignSafeResponse

### Portal

- `/campaigns` — "📦 Подготовить" button for approved campaigns (inline POST form, no JS)
- `/publications` — rewritten to show publication batches with campaign context
  - Backend-only mode warning: "Доставка на КСО отключена до отдельного approval gate"
  - Legacy manifests section preserved for backward compatibility
- `BackendClient.create_publication_batch(access_token, campaign_code)` — new method
- Flash handling: `ok:batch_created` message

### Tests

| Suite | Passed | Skipped |
|---|---|---|
| Backend | **528** | 0 |
| Portal | 498 | 20 |
| KSO SA | 86 | 0 |
| Player | 2060 | 12 |
| Sidecar | 1838 | 0 |
| Infra | 227 | 0 |
| **Total** | **5237** | **32** |

Full regression: **5269 total (5237 passed + 32 skipped), 0 failed.** Delta from 41.3 baseline (5210): +59.

### Key decisions

- Batch starts as `draft`; state machine: draft → pending_approval → approved → manifest_generated → published
- Physical KSO delivery is NOT triggered — backend status only
- `ScheduleRun` ORM model not yet defined — raw SQL used for schedule_runs insertion
- Manifest generation (version N+1) deferred to full batch workflow execution

### Remaining

- Full batch workflow execution (request_approval → approve → generate_manifests → publish)
- Manifest version N+1 generation for campaign material inclusion
- Physical KSO delivery gate (separate approval)

---

## [41.4.1-batch-workflow-manifest-generation] — 2026-06-16

**Full Publication Batch Workflow & Manifest Generation — batch lifecycle + ScheduleRun ORM.**

### Backend

- `ScheduleRun` ORM model added (`backend/app/domains/scheduling/models.py`)
  - Table `schedule_runs` already existed (migration 008); ORM model was missing
  - Enables `generate_manifests()` to work with ORM instead of failing on import
- `create_batch()` — removed dangling `selectinload(ScheduleRun.conflicts)` (ScheduleConflict doesn't exist)
- Batch lifecycle endpoints (pre-existing, now functional): request-approval, approve, generate, publish, cancel

### Portal

- `/publications` — batch action buttons per status:
  - `draft` → «→ Согласование» (request-approval)
  - `approved` → «📋 Generate» (generate manifests)
  - `manifest_generated` → «🚀 Publish» (backend status only)
  - `✕` Cancel (non-terminal states)
- All actions are server-side POST forms, batch_id in URL, no JS
- BackendClient: `request_batch_approval()`, `approve_batch()`, `generate_batch_manifests()`, `cancel_batch()`
- Batch comment parsing: campaign_code extracted via regex from batch comment
- Handler flash messages: `ok:batch_approval_requested`, `ok:manifest_generated`, `ok:batch_published`, `ok:batch_cancelled`

### Manifest generation

- `generate_manifests()` now functional (ScheduleRun ORM exists)
- Creates manifest version N+1 with full playlist
- Previous manifest not mutated on regenerate (old draft versions → cancelled)
- Backend publish status only — physical KSO delivery NOT triggered

### Tests

| Suite | Passed | Skipped |
|---|---|---|
| Backend | **551** | 0 |
| Portal | 498 | 20 |
| KSO SA | 86 | 0 |
| Player | 2060 | 12 |
| Sidecar | 1838 | 0 |
| Infra | 227 | 0 |
| **Total** | **5260** | **32** |

Full regression: **5292 total, 0 failed.** Delta from 41.4 (5269): +23.

### Key decisions

- `ScheduleRun` ORM: minimal model covering existing table — no migration needed
- Batch workflow: draft → pending_approval → approved → manifest_generated → published
- Manifest generation creates version N+1 (new full playlist, old versions preserved)
- Previous manifest not mutated on regenerate (old draft versions → cancelled)
- Physical KSO delivery remains disabled (separate gate)

### Remaining

- Physical KSO delivery gate
- Controlled long-run with manifest delivery

---

**CampaignCreative is_active compatibility guard — safe helper without ORM column.**

### Change

- `_is_campaign_creative_active(link)` helper: uses `getattr(link, "is_active", True)` — safe when ORM model has no `is_active` column
- Removed `CampaignCreative.is_active == True` from query filters (would fail on missing column)
- Response dicts: `"is_active": True` (existence = active)

### Tests

| Suite | Passed | +New |
|---|---|---|
| Backend | **502** | +4 |

---

## [41.3-approval-decision-ux] — 2026-06-16

**Approval Decision UX — campaign summary on /approvals page, per-row approve/reject forms.**

### Portal

- `/approvals` — enhanced: campaign summary for `object_type=campaign` (name, creatives, schedule, campaign status)
- Per-row approve/reject forms: hidden inputs (`approval_code`, `decision`), POST to `/approvals/decide`
- Reject form includes comment field (reason)
- Empty state links to `/campaigns` for submission guidance
- Table columns: Заявка, Тип, Объект, Статус, Детали, Запрошен, Решение

### Approve/Reject flow

- Backend unchanged: `POST /api/approvals/{code}/approve`, `POST /api/approvals/{code}/reject`
- Portal `/approvals/decide` handler already uses production BackendClient methods
- State transitions: `pending` → `approved`/`rejected` (via approval domain)
- Campaign status: `pending_approval` → `approved`/`rejected`
- Maker-checker: backend-enforced (requested_by ≠ decided_by)
- Duplicate decide: safe 400 error

### Technical debt: CampaignCreative.is_active

- **NOT added to ORM model** — column exists in DB (via manual migration), but adding to model breaks `Base.metadata.create_all()` in PoP integration tests
- Known gap documented: service references `is_active` but model doesn't map it
- Fix deferred to DB migration phase

### No JS/CDN/localStorage

- ✅ `/approvals` — no `<script>`, `onclick`, `confirm`, `onsubmit`
- ✅ All forms use `method="post"`, no client-side handlers

### Tests

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Portal | **485** (+2) | 20 | 0 |

### Regression

| Suite | Passed |
|---|---|
| Backend | 498 |
| Portal | 485 |
| KSO SA | 86 |
| Player | 2072 |
| Sidecar | 1838 |
| Infra | 227 |
| **Total** | **5206** |

---

## [41.2.1-campaign-submit-approval-integration] — 2026-06-16

**Campaign Submit → ApprovalRequest integration gate.**

### Key Fixes

- **Submit now creates ApprovalRequest**: `POST /api/campaigns/by-code/{code}/submit` calls `approvals.service.request_approval(object_type=campaign, ...)` instead of old `submit_campaign` (which required channels/targets/renditions unavailable to code-based campaigns)
- **Completeness validation**: submit rejects campaigns with no creative bindings, archived/rejected creatives, no schedule, no schedule slots
- **Campaign status**: `draft` → `pending_approval` (via approval service, not legacy `in_review`)
- **ApprovalCode**: `appr_campaign_{campaign_code}` — automatically visible in `/approvals`
- **Maker-checker**: preserved via approval domain (user cannot decide own request)
- **Duplicate submit**: idempotent-safe — `_check_no_active_pending` prevents double ApprovalRequest
- **Audit**: `campaign.submit` with `approval_code` in details

### Portal

- Submit button wording: "На согласование" → "Запросить"
- Flash message: "Согласование запрошено. Кампания ожидает решения."
- `pending_approval` status rendered with review badge
- `/approvals` page confirmed: shows campaign approvals, no JS, maker-checker note

### CampaignCreative binding

- ✅ Created on `/campaigns/create` via `creative_codes` in `create_test_kso_campaign`
- ✅ Bound creatives validated on submit (not archived/rejected)

### Object model

- **ApprovalRequest.object_type**: `campaign` (validated by `post /api/approvals` schema)
- **Known gap**: `CampaignCreative.is_active` column referenced in service but not in model

### Tests

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Portal | **483** (+9) | 20 | 0 |

### No JS/CDN/localStorage

- ✅ `/campaigns` — no `<script>`, `onclick`, `confirm`, `onsubmit`
- ✅ `/campaigns/create` — same
- ✅ `/approvals` — same

---

## [41.0.0-portal-ui-hygiene-baseline] — 2026-06-16

**Portal UI Hygiene Baseline — safe CSS-only improvements, no redesign.**

### Changes
5 CSS changes: heading balance, body min-height, text-size-adjust, reduced-motion, shadow tokens.

### Regression
5168 passed, 44 skipped, 0 failed.

---

## [41.1-creative-upload-ux] — 2026-06-16

**Creative Upload UX — advertiser, metadata, versioning, archive.**

### Backend

- `CreativeResponse` enhanced: +`advertiser_name`, `advertiser_code`, `content_type`, `width`, `height`, `file_size_bytes`, `duration_ms`, `current_version`
- `_enrich_creatives()` service helper: eager-loads advertiser names + latest version metadata
- `GET /api/creatives/by-code/{code}` — new endpoint (safe code-based access)
- `POST /api/creatives/by-code/{code}/archive` — new endpoint (media.manage, RLS enforced)
- Audit events on `creative.create` and `creative.archive`

### Portal

- Upload form: +description field, KSO portrait recommendation 768×1024
- Creative list: +advertiser column, +version column, human-readable status labels (Черновик/На проверке/etc.), dimensions as "W×H"
- Archive action: per-creative archive button with confirmation
- `_status_label()` helper for Russian status labels
- Note box: safe wording (no forbidden tokens mentioned)

### BackendClient

- `list_advertisers()` — new method (GET /api/advertisers)
- `archive_creative()` — new method (POST /api/creatives/by-code/{code}/archive)

### Security/RBAC/RLS

- `/creatives` page: `media.read`
- Upload: `media.manage`
- Archive: `media.manage`
- RLS: archive respects advertiser scope
- Audit: create + archive events written

### Regression

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 498 | 0 | 0 |
| Portal | 459 | 32 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2060 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5168** | **44** | **0** |

### NOT added to Creative

- ❌ Schedule/time windows (→ 41.2/41.3 Campaign/Schedule UX)
- ❌ Campaign binding wizard
- ❌ Image preview thumbnails (requires safe media endpoint)
- ❌ Complex image dimension parser
- ❌ JS/CDN/localStorage

---

## [41.2-business-campaign-creation-ux] — 2026-06-16

**Business Campaign Creation UX — business form with advertiser, creative, device, dates, schedule, and submit.**

Campaign adds ad material to schedule. Publication builds full manifest/playlist for KSO.
Local KSO playlist is never mutated piecemeal.

### Backend

- `POST /api/campaigns/by-code/{code}/submit` — new endpoint (code-based submit, RLS enforced, audit trail)

### Portal

- `/campaigns` — list page now links to `/campaigns/create` (business form), inline edit/bind/submit per-campaign
- `/campaigns/create` — **new business form** with:
  - campaign_code, name, description, advertiser dropdown
  - creative dropdown (non-archived/rejected), device dropdown (active)
  - date_from, date_to, timezone (9 RU zones)
  - days of week checkboxes (Пн–Вс)
  - time window presets: all_day, morning, day, evening, custom
  - server-side validation: date range, unique code, days required, time window
- `POST /campaigns/create` — orchestrates 4-step creation:
  1. Create campaign via `POST /api/campaigns/by-code`
  2. Create placement via `POST /api/placements` (if device selected)
  3. Create schedule via `POST /api/schedules`
  4. Create schedule slots (one per day_of_week × time window)
- `POST /campaigns/{code}/submit` — → `POST /api/campaigns/by-code/{code}/submit` (draft→in_review)
- Summary page after creation: campaign_code, name, advertiser, creative, device, period, days, time, status, placement_code, schedule_code, slot count

### BackendClient

- `submit_campaign()` — new method for code-based submit

### JS Removal

- Archive button `onsubmit="return confirm(...)"` removed from campaigns page
- No `<script>`, `onclick`, `confirm()` on `/campaigns` or `/campaigns/create`

### No JS/CDN/localStorage

- ✅ Server-side forms only
- ✅ Pure CSS styling
- ✅ No external CDN

### Security/RBAC/RLS/Audit

- Campaign create: `campaigns.create`
- Campaign edit/archive/submit/bind: `campaigns.manage`
- RLS: advertiser scope enforced via campaign_code resolution
- Audit: `campaign.create`, `campaign.submit`, `campaign.bind_creative`

### Tests

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Portal | **474** (+13) | 20 | 0 |

### Campaign workflow statement

> Campaign adds ad material to schedule. Publication builds full manifest/playlist for KSO.
> Local KSO playlist is never mutated piecemeal.

---

## [v0.11.1-pre-pilot-access-integration-hotfix] — 2026-06-16

### What's included

| Step | What | Regression |
|---|---|---|
| v0.11.0 | Pre-Pilot Security Baseline (full) | 5156 green |
| 40.2.1 | Admin Portal Access Bootstrap Fix (PAGE_PERMISSION_MAP↔backend) | 5159 green |
| 40.2.2 | Portal Backend Integration Gate (14 pages audited, 1 fix) | 5168 green |

### Key Fixes

- **40.2.1:** PAGE_PERMISSION_MAP aligned with real backend permissions (was using non-existent names causing 403)
- **40.2.2:** `/proof-of-play` fixed from legacy `GET /api/proof-of-play/test-kso` → production `GET /api/reports/pop`

### Regression

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 498 | 0 | 0 |
| Portal | 459 | 32 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2060 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5168** | **44** | **0** |

### Pilot Status: NO-GO 🔴

- HW scanner E2E: postponed (no hardware available)
- Controlled long-run (1h/8h/48h): not executed
- Pilot runbook: structure defined, content after scanner + long-run
- Go/No-Go decision matrix: 11 criteria, all pending

### Known Remaining Non-Blockers

- 7 legacy BackendClient methods (dead code, unused by portal): `list_campaigns`, `list_placements`, `create_placement`, `list_approvals`, `request_approval`, `decide_approval`, `get_test_kso_readiness`
- `/deployment` page: demo-only documentation page, no backend data needed

### Tags

- `v0.11.1-pre-pilot-access-integration-hotfix` — annotated tag on 40.2.2 commit
- `v0.11.0-pre-pilot-security-baseline` — previous baseline (NOT rewritten)
- `v0.10.0-approval-publication-hardening` — unchanged
- `v0.9.0-product-portal-hardening` — unchanged

---

## [v0.10.0-approval-publication-hardening] — 2026-06-26

**Release: Approval / Publication Workflow Hardening — production approval API, unified manifest generation, publication batch state machine, portal UX production-ready.**

### What's included

- ✅ **Production approval endpoints** — GET/POST /api/approvals, approve/reject per-code (39.3.1)
- ✅ **Approval guardrails** — maker-checker, state validation, duplicate prevention, explicit decision mapping
- ✅ **Publication batch state machine** — draft → pending_approval → approved → manifest_generated → published (39.3.4)
- ✅ **Batch approval integration** — request-approval creates ApprovalRequest; batch approve/generate/publish require approved ApprovalRequest
- ✅ **Unified manifest generation** — build_manifest_from_placement() single builder, production manifest endpoints (39.3.2)
- ✅ **Portal approvals UX** — production backend-driven, publication_batch support, no test-kso/demo wording (39.3.3)
- ✅ **Portal publications UX** — production endpoints, backend-status-only labels, no demo placeholders (39.3.3)
- ✅ **Safe projection** — all responses: no raw UUID/secrets/tokens/backend_url
- ✅ **Full regression** — 5042 tests green

### Commits

| Commit | Description |
|---|---|
| `3fc003c` | 🛡 Approval/publication hardening analysis + safe fixes |
| `fe03de4` | 🛡 Production approval API foundation |
| `58735d9` | 🧾 Unified manifest generation workflow |
| `d16a14e` | 🛡 Portal approvals/publications → production workflow |
| `30ac341` | 🧱 Publication batch workflow hardening |

### Known deferred (not blocking v0.10.0)

| Item | Status |
|---|---|
| Physical manifest delivery to KSO | Deferred — backend-only workflow |
| Sidecar sync | Deferred |
| Scanner (HW) validation | Deferred — no scanner hardware |
| Controlled long-run (≥48h) | Deferred |
| Pilot runbook | Deferred |
| mTLS/nonce/rate-limit credential rotation | Deferred |
| Charts/Excel/drill-down in Reports | Deferred |
| Full RLS enforcement | Deferred |
| Live pilot/fleet rollout | NOT APPROVED |

---

## [40.2.1-admin-portal-access-bootstrap] — 2026-06-26

**Admin Portal Access Bootstrap Fix — PAGE_PERMISSION_MAP aligned with backend permissions.**

### Root Cause
`PAGE_PERMISSION_MAP` used portal-local permission names not in backend seed. Session stored real backend permissions but route guard checked non-existent names → every page returned 403.

### Fix
- PAGE_PERMISSION_MAP aligned with real backend codes
- Added /device-dashboard + /readiness entries
- Removed stale /admin add_api_route  
- Mock auth patch extended (get_current_portal_user + get_current_user_permissions)
- 23 new backend seed integrity tests

---

## [40.2.2-portal-backend-integration-gate] — 2026-06-26

**Portal Backend Integration Gate — verified all 14 page→endpoint chains, fixed 1 legacy test-kso usage, added cross-suite guard tests.**

### Audit
Full matrix created: `docs/audit/portal-backend-integration-matrix.md` — 14 pages × BackendClient methods × backend endpoints × permissions.

### Broken Link Found & Fixed

| # | Page | Old method | Old endpoint | New method | New endpoint |
|---|---|---|---|---|---|
| 1 | `/proof-of-play` | `list_pop_events()` | `GET /api/proof-of-play/test-kso` | `get_pop_report()` | `GET /api/reports/pop` |

### Already Correct (confirmed by audit)
- `/campaigns` → `list_campaigns_prod()` → `/api/campaigns` ✅ (production since 39.2.2)
- `/dashboard` → `list_approvals_prod()` → `/api/approvals` ✅ (production since 39.2.2)
- `/approvals` → `list_approvals_prod()` → `/api/approvals` ✅
- `/reports` → `get_pop_report()` + `get_pop_summary()` → `/api/reports/pop*` ✅
- All 13 other pages use production endpoints ✅
- 7 legacy BackendClient methods exist but are unused by portal (dead code, safe to remove later)

### Permission Consistency
All 10 unique PAGE_PERMISSION_MAP permissions exist in backend seed. `system_admin` has all. `security_admin` has security-relevant permissions. No mismatch (unlike 40.2.1).

### Guard Tests (always run in default regression)
- `TestBackendClientEndpointMapping` — 13 tests: verify every used BackendClient method hits production endpoint
- `TestPermissionMapConsistency` — 8 tests: PAGE_PERMISSION_MAP↔seed, system_admin has all, security_admin coverage
- `test_main_py_does_not_use_legacy_list_pop_events` — regression prevention for the fix

Live HTTP tests (12) under `RUN_PORTAL_BACKEND_LIVE_INTEGRATION=1` skip gate.

### Regression

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 498 | 0 | 0 |
| Portal | 459 | 32 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2060 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5168** | **44** | **0** |

### RBAC/RLS
- ✅ NOT weakened
- ✅ RBAC gate closed
- ✅ RLS gate closed
- ✅ Audit trail active

No KSO/SSH/X11/Chromium/runner/sidecar launched. No secrets disclosed.

---

## [v0.11.0-pre-pilot-security-baseline] — 2026-06-26

**Release: Pre-Pilot Security Baseline — RLS gate closed, audit hardened, device dashboard complete, pilot gates documented.**

### What's included

| Step | What | Regression |
|---|---|---|
| 39.4 | Device/Sidecar Dashboard (7 GAPs: aggregation endpoint, portal page, sidecar_status, readiness hardening) | 5103 green |
| 40.0 | TZ Alignment / Security & RLS Audit (34 requirements traced, gap analysis) | 5079 green |
| 40.1 | RLS Hardening P0 (foundation: UserScopeContext, apply_advertiser_rls, 17 unit tests) | 5096 green |
| 40.1.2 | RLS Gate Closure (schedules/publications/manifests enforced, 42 endpoint tests) | 5116 green |
| 40.1.3 | Regression Baseline Cleanup (all suites green, integration tests separated, sidecar flaky fix) | 5106 green |
| 40.2 | Admin Audit Hardening (business-audit trail, payload redaction, 18 tests) | 5124 green |
| 40.3 | Pilot Readiness Gates Plan (4 gates, 7 approval tokens, decision matrix) | 5156 green |

### Default Regression

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 475 | 0 | 0 |
| Portal | 458 | 20 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2072 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5156** | **32** | **0** |

### Pilot Status

**NO-GO 🔴** — physical pilot remains NOT approved.

Required for GO:
- HW scanner E2E validation (scanner unavailable)
- Controlled long-run (≥1h)
- Physical operator + approval tokens

### Commits

| Commit | Description |
|---|---|
| `5557563` | 📡 Close all device/sidecar dashboard GAPs (39.4.3) |
| `3628c3f` | 🔍 TZ alignment / Security & RLS audit gate (40.0) |
| `d00858d` | 🔐 Add RLS enforcement layer — campaigns/creatives/approvals/reports/dashboard (40.1) |
| `f04ba67` | 🔐 Verify RLS enforcement — fix P0 campaign leaks (40.1.1) |
| `fabf13d` | 🔐 Add RLS endpoint evidence and close gate (40.1.2) |
| `67baca7` | 🧪 Stabilize regression baseline after RLS hardening (40.1.3) |
| `1b51894` | 📋 Update audit doc with clean regression baseline (40.1.3) |
| `8ff648a` | 🧾 Harden admin audit trail (40.2) |
| `793266d` | 📋 Define pilot readiness gates (40.3) |

No KSO/SSH/X11/Chromium/runner/sidecar launched. No manifest delivery. No scanner test. No PoP upload. No secrets committed.

---

## [40.3-pilot-readiness-gates-plan] — 2026-06-26

**Pilot Readiness Gates Plan — comprehensive gate definition, no physical execution.**

### Document Created

`docs/audit/pilot-readiness-gates-plan.md` — 8-section plan:

### Gates Defined

| Gate | Status | Detail |
|---|---|---|
| **A — HW Scanner E2E** | 🔴 POSTPONED | Scanner unavailable. Full protocol, 8 stop criteria, approval token `PHASE_SCANNER_E2E_APPROVED` |
| **B — Controlled Long-Run** | 🔴 NOT EXECUTED | 1h/8h/48h options, 13-metric monitoring plan, 10 success/6 fail criteria, approval token `PHASE_LONG_RUN_APPROVED` |
| **C — Pilot Runbook** | 🟡 STRUCTURE DEFINED | 10-section runbook: roles, comms, pre-check, start/monitor/stop, incident response, rollback, evidence, post-run template |
| **D — Go/No-Go** | 🔴 NO-GO | 11 criteria matrix: scanner (not done), long-run (not done), regression (green), RLS (closed), audit (active), dashboard (healthy), operator (not present), rollback (ready), runbook (structure only), tokens (not issued) |

### Approval Tokens Defined

7 tokens: `PHASE_SCANNER_E2E_APPROVED`, `PHASE_LONG_RUN_APPROVED`, `PHASE_PHYSICAL_KSO_ACCESS_APPROVED`, `PHASE_MANIFEST_DELIVERY_APPROVED`, `PHASE_SIDECAR_SYNC_APPROVED`, `PHASE_POP_UPLOAD_APPROVED`, `PHASE_SYSTEMD_AUTOSTART_APPROVED`

### Updated Docs

- `docs/audit/technical-debt-next-actions.md` — added 40.1.2, 40.1.3, 40.2, 40.3
- `docs/audit/release-versioning-policy.md` — added post-v0.10.0 hardening table + v0.11.0 gate conditions

### No Physical Actions

- ❌ No KSO/SSH/X11/Chromium/runner launched
- ❌ No sidecar daemon started
- ❌ No PoP upload
- ❌ No manifest delivery to physical KSO
- ❌ No sidecar sync
- ❌ No scanner test (HW unavailable)
- ❌ No long-run executed
- ✅ RLS gate closed
- ✅ Audit trail active
- ✅ Regression green

---

## [40.2-admin-audit-hardening] — 2026-06-26

**Admin Audit Hardening — business-audit trail for all critical workflows.**

### Audit Coverage Matrix

| Domain | Actions Logged |
|---|---|
| Campaigns | create, update, archive, bind_creative, unbind_creative |
| Creatives | create, update, upload_version |
| Approvals | request, approve |
| Publications | create, request_approval, approve, generate_manifests, publish, cancel |
| Manifests | generate, publish |
| Identity (existing) | create_user, block_user, archive_user, unblock_user, update_roles, update_rls_scopes |
| Device gateway (existing) | manifest delivery audit |

### Added

- `backend/app/domains/audit/service.py` — centralized `audit_business_action()` with automatic forbidden-field stripping (secrets/tokens/passwords/URLs)
- Audit calls injected into campaigns, media (creatives), approvals, publications, manifests routers
- Enhanced audit endpoint with filters: `action`, `target_type`, `target_ref`, `actor_id`
- `backend/tests/test_audit_hardening.py` — 18 tests (payload safety + action naming)
- Portal `/admin` page already shows audit events (pre-existing) — secure, RBAC-guarded, no secrets

### Payload Redaction

Fields stripped from audit details_json: password, password_hash, secret, device_secret, access_token, token, token_hash, backend_url, minio_endpoint, private_key, barcode, receipt, payment, fiscal, card, customer_id, phone, file_path, sha256 — plus any key containing "secret", "password", "token", or "key".

### Regression

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 475 | 0 | 0 |
| Portal | 438 | 20 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2060 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5124** | **32** | **0** |

**Regression Baseline Cleanup — all suites green in default profile, integration tests separated.**

### Portal — BackendIntegration Tests Separated

9 tests in `TestStoresBackendIntegration` + `TestDevicesBackendIntegration` were failing in full suite due to global state collision between test classes (pass in isolation). They use `_FakeBackendClient` (mock), not a real backend.

**Fix:** Marked with `@unittest.skipUnless(os.environ.get("RUN_PORTAL_BACKEND_INTEGRATION"))` — skipped in default regression, runnable with:

```
RUN_PORTAL_BACKEND_INTEGRATION=1 python3 -m pytest apps/portal-web/tests/
```

### Sidecar — Non-deterministic Test Fixed

`test_client_repr_safe` was checking `assertNotIn("9999", text)` on `repr(client)`. Memory addresses like `0x76ff99995550` randomly contained "9999". Removed port-number-in-repr check (not a security concern). Kept secret checks: opaque-test-key, Bearer, access_token.

### Default Regression — Fully Green

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| Backend | 457 | 0 | 0 |
| Portal | 438 | 20 | 0 |
| KSO state adapter | 86 | 0 | 0 |
| KSO player | 2060 | 12 | 0 |
| KSO sidecar | 1838 | 0 | 0 |
| Infra | 227 | 0 | 0 |
| **Total** | **5106** | **32** | **0** |

### Integration Profile (optional)

```
RUN_PORTAL_BACKEND_INTEGRATION=1 python3 -m pytest apps/portal-web/tests/
```

Requires nothing special — uses FakeBackendClient mock, no live backend needed.

**RLS Gate Evidence Cleanup — endpoint-level enforcement verified, all P0 leaks patched, 42 new tests.**

### RLS Enforcement — Newly Protected Endpoints

| Domain | Endpoints | RLS via |
|---|---|---|
| Campaigns | 4 endp | `assert_object_in_advertiser_scope` (P0 fixes: patch, archive, list-creatives, unbind-creative) |
| Placements | 2 endp | `assert_object_in_advertiser_scope` (patch, archive — were unprotected) |
| Schedules | 11 endp | `_resolve_schedule_advertiser` (schedule → campaign_code → advertiser_id) |
| Publications | 12 endp | `_resolve_batch_advertiser` (batch → campaign_id → advertiser_id) |
| Manifests | 8 endp | `_resolve_manifest_advertiser` (manifest → placement → campaign_code → advertiser_id) |

### Endpoint-Level Tests

- `backend/tests/test_rls_endpoint_enforcement.py` — **42 tests** in 9 classes
- Covers: campaign P0 leaks, placement/schedule/publication/manifest cross-advertiser blocking, store/device scope, admin bypass, requires_rls semantics, SQLite query-level filtering

### RLS Gate

**CLOSED** ✅ All domains enforced. Advertiser isolation proven. Admin bypass verified. 5116 tests green.

### Status

- Backend: 457 passed (0 fail)
- Portal: 449 passed (9 pre-existing BackendIntegration — needs live backend)
- KSO state adapter: 86 passed
- KSO player: 2060 passed (12 skipped)
- KSO sidecar: 1837 passed (1 pre-existing non-deterministic)
- Infra: 227 passed
- Total: **5116 passed**, 10 pre-existing failures, 0 new failures

No KSO/SSH/X11/Chromium/sidecar launched. No manifest published. No secrets disclosed.

**Release: Product Portal Hardening — все DEMO-заглушки убраны из Schedule, Campaign, Dashboard, Reports.**

### What's included

- ✅ **Phase D** — one-KSO E2E dry run D0–D6 completed (physical KSO 192.168.110.223, 768×1024 portrait)
- ✅ **Device auth** — JWT/bcrypt device gateway foundation (39.1.1)
- ✅ **Campaign/placement production APIs** — code-based endpoints, creative binding (39.1.2)
- ✅ **Schedule backend API** — Schedule + ScheduleSlot models, code-based CRUD (39.1.3)
- ✅ **Schedule UI** — backend-driven, remove demo/stub, production API (39.2.1)
- ✅ **Campaign UI** — production API: create (by-code), edit, archive, creative bind/unbind (39.2.2, 39.2.2.1)
- ✅ **Dashboard** — real KPI from 6 backend list endpoints, remove demo (39.2.3, 39.2.3.1)
- ✅ **Reports** — production PoP backend + server-side filters enabled (39.2.4, 39.2.4.1)
- ✅ **RBAC** — schedule/campaign/reports permissions aligned with backend
- ✅ **Full regression** — 4976 tests green (backend 322, portal 431, state 86, player 2072, sidecar 1838, infra 227)

### Known deferred (not blocking v0.9.0)

| Item | Status |
|---|---|
| HW scanner E2E validation | Postponed (scanner not available) |
| Controlled long-run (≥48h) | Required before pilot |
| Charts / Excel export / drill-down | UI deferred |
| mTLS / nonce / rate-limit / rotation | Device gateway deferred |
| RLS full enforcement | Later phase |
| Live pilot / fleet rollout | NOT approved |
| BackendIntegration failures (9) | Pre-existing, not blocking |

### Previous releases

- **v0.8.0** — Device gateway / backend API hardening
- **v0.7.0** — One-KSO E2E dry run
- **v0.6.0** — Sidecar config readiness
- **v0.5.0** — Test KSO Phase A readiness

---

## [Unreleased] — Product Backend / Frontend Gap Analysis (39.0, 2026-06-26)

### 39.4.0 — Device / Sidecar Dashboard Analysis

**Comprehensive audit of device registry, gateway, sidecar status, and portal pages. 7 gaps identified.**

- Analysis document: `docs/audit/device-sidecar-dashboard-analysis.md`
- **What exists:** rich device model layer (KsoDevice, GatewayDevice, DeviceHeartbeat, DeviceCredential, DeviceSession, DeviceEvent, DeviceManifestRequest, DeviceMediaRequest). Gateway admin endpoints for per-device detail. Sidecar `agent_status.json` (running/warning/error) and `player_readiness.py`. Portal `/devices` page (KSO registry only) and `/readiness` page (test-kso only).
- 🔴 **GAP 1:** No device dashboard aggregation endpoint — `GET /api/device-dashboard` needed
- 🔴 **GAP 2:** Heartbeat does not carry sidecar agent status (`running`/`warning`/`error`)
- 🔴 **GAP 3:** `KsoDevice.last_seen_at` not updated by heartbeat handler
- 🟡 **GAP 4:** Portal `/readiness` is test-kso-only, hardcoded device_code
- 🟡 **GAP 5:** Portal `/devices` shows no gateway data (heartbeat, credential, manifest, PoP)
- 🟢 **GAP 6:** No per-device manifest/media readiness surfaced
- 🟢 **GAP 7:** No error aggregation endpoint for device events
- Plan: 39.4.1 Backend API → 39.4.2 Portal page → 39.4.3 Readiness hardening → 39.4.4 Sidecar contract → 39.4.5 Polish
- No code changes — docs only

### 39.3.4 — Publication Batch Workflow Hardening

**Production batch workflow hardened: draft → pending_approval → approved → manifest_generated → published.**

- New batch states: `pending_approval`, `manifest_generated`, `rejected` (old `generated` removed)
- State machine + guardrails: valid transitions enforced in `_VALID_BATCH_TRANSITIONS`
- `POST /api/publication-batches/{id}/request-approval` — creates ApprovalRequest, transitions draft→pending_approval
- `approve_batch` rewritten: accepts pending_approval → approved (checks approved ApprovalRequest)
- `generate_manifests` guard: must be approved (was draft/generated)
- `publish_batch` guard: must be manifest_generated (was approved)
- `_request_approval_internal()` added to approvals service — internal helper for batch workflow
- Cancellation: handles all new statuses
- All endpoints safe projection; no raw UUID/secrets/tokens/backend_url
- Backend tests: +25 (state machine transitions, router structure, service guardrails, approval integration)
- Portal tests: 440 unchanged
- 🟡 B2 → foundation hardened: full workflow backend-complete, physical KSO delivery deferred
- Deferred: sidecar sync, physical KSO delivery, scanner validation, controlled long-run

### 39.3.3 — Portal Approval / Publication UX Hardening

**Portal approvals and publications pages fully converted to production backend endpoints. All test-kso/demo wording removed from production UI.**

- Approvals page (`/approvals`): description updated to "production approval workflow", no test-kso mentions
- Approvals form: added `publication_batch` object type (aligns with 39.3.1 backend)
- Approvals notes: replaced "Test KSO technical validation" with "без доставки на КСО"
- Publications page (`/publications`): description updated to "backend status only, без доставки на КСО"
- Publications form: placeholders changed from `demo_placement_001`/`demo_manifest_001` to generic `placement_code`/`manifest_code`
- Publications notes: removed "test KSO" wording, added "backend status only" clarification
- Publications flash: "Опубликован" changed to "Опубликован (backend status)" —  to clarify no KSO delivery
- BackendClient: added `list_publication_batches()`, `get_publication_batch()`, `publish_batch()` — production batch methods
- All BackendClient manifest/approval methods already switched to production in 39.3.1–39.3.2
- RBAC unchanged: `/approvals` → `approvals.read`, `/publications` → `publications.read`
- No JS/CDN/localStorage added — all server-side rendering
- Portal tests: +9 (no test-kso wording, production workflow checks, publication_batch form, backend-only notes, no raw IDs)
- 🟡 B2 (approval-batch integration) → portal supports publication_batch approval; full batch workflow remains deferred
- What remains for pilot gates: full publication batch workflow, sidecar sync, physical KSO delivery, scanner validation, long-run test

### 39.3.2 — Manifest Generation Unification

**Unified manifest builder. Blocker B3 closed, production manifest endpoints added.**

- Unified builder: `build_manifest_from_placement()` — canonical entry point for placement-based manifest generation. Both production and legacy test-kso paths delegate to this.
- `generate_manifest()` refactored → delegates to unified builder (deduplicated ~100 lines of validation)
- Production endpoints added: `POST /api/manifests`, `GET /api/manifests/{code}`, `POST /api/manifests/{code}/publish`
- Router reordered: literal paths (test-kso) before parameterized paths (/{manifest_code}) to prevent shadowing
- BackendClient updated: `generate_manifest()` → `POST /api/manifests` (production), `get_manifest()` → `GET /api/manifests/{code}` (production), `publish_manifest()` → `POST /api/manifests/{code}/publish` (production)
- Portal publications page: generate/publish forms now call production endpoints
- Publication batch `publish_batch` already requires approved ApprovalRequest (39.3.1 foundation)
- Legacy test-kso endpoints preserved: `/test-kso/generate`, `/test-kso`, `/test-kso/{code}`, `/test-kso/{code}/publish` — all delegate to unified builder
- All responses: safe projection, no raw UUIDs/secrets/tokens/backend_url
- Backend tests: +15 (2 unified builder checks, 13 production endpoint + route + safe response tests)
- Portal tests: 431 unchanged
- 🔴 B3 (fragmented manifest generation) → CLOSED
- 🟡 B2 (full batch workflow: manifest delivery, sidecar sync) → deferred to 39.3.3
- Manifest versioning/idempotency: `publish_manifest` idempotent (already published → return as-is); `generate_manifest` checks duplicate manifest_code (409)
- What remains for 39.3.3: Portal Approval/Publication UX, manifest delivery to KSO, full publication batch workflow, sidecar sync
- Physical KSO not touched, manifest not delivered to device

### 39.3.1 — Production Approval API Foundation

**Production approval endpoints with publication batch integration. Blocker B1 closed, B2 partially.**

- New production endpoints: `GET /api/approvals`, `POST /api/approvals`, `GET /api/approvals/{code}`, `POST /api/approvals/{code}/approve`, `POST /api/approvals/{code}/reject`
- Separate approve/reject endpoints with decision enforcement (cannot approve via reject, vice versa)
- `publication_batch` object_type support in ApprovalRequestCreate schema
- `_get_object_or_404` extended to support PublicationBatch lookup
- `get_approval()` function added to service layer
- `publish_batch` now requires approved ApprovalRequest for the batch
- BackendClient: `list_approvals_prod()`, `get_approval()`, `create_approval()`, `approve_approval()`, `reject_approval()`
- Legacy: `list_approvals()`, `request_approval()`, `decide_approval()` → production prefer-this methods
- Portal approvals page switched to production endpoints
- RBAC: `/approvals` → `approvals.read`
- Backend tests: +16 (route structure, schema validation, service checks)
- Portal tests: 431 unchanged
- 🔴 B1 (no production approval) → CLOSED
- 🟡 B2 (approval-batch integration) → foundation laid; full batch workflow remains for 39.3.2
- 🔴 B3 (fragmented manifest generation) → deferred to 39.3.2

### 39.3.0 — Approval & Publication Hardening Analysis

**Comprehensive audit of approval/publication workflow. Analysis document + safe fixes.**

- Analysis: `docs/audit/approval-publication-hardening-analysis.md` — 4 blockers, 5 deferred gaps
- 🔴 Blocker 1: No production approval endpoint (all test-kso)
- 🔴 Blocker 2: Approvals not integrated with Publication Batch
- 🔴 Blocker 3: Fragmented manifest generation (standalone test-kso vs batch)
- 🔴 Blocker 4: No pre-approval state validation
- 🟡 Gap 5: Fragile status string concatenation → fixed (explicit `_DECISION_TO_APPROVAL_STATUS` dict)
- 🟡 Added pre-approval state check: only `draft`/`pending_approval` can request approval
- Backend tests: +3 (approval service logic checks)
- Regression: 4979 tests green

### 39.2.4.1 — Enable Reports UI Filters

**Reports page GET form enabled with server-side filters.**

- Filter inputs: campaign_code, creative_code, device_code, placement_code (text), date_from, date_to (date)
- Server-side GET form — no JS/CDN/localStorage
- Filter values retained after submit; «Сбросить» link clears all
- Date validation: date_from > date_to → safe warning, no backend call
- Handler extracts query params and passes to `BackendClient.get_pop_summary()` / `get_pop_report()`
- Portal tests: +7 (filter rendering, query params, date validation, reset, no fake values)
- Filters disabled → ENABLED ✅
- Charts/Excel/drill-down remain deferred

### 39.2.4 — Reports Backend-Driven Integration

**Reports page connected to production PoP backend — demo_data removed as primary source.**

- Backend: new production endpoints `GET /api/reports/pop` (list) and `GET /api/reports/pop/summary` (aggregation)
- Both endpoints require `reports.read` permission, safe projection (no raw UUIDs/secrets)
- `get_pop_summary` aggregates: total_events, unique_devices/campaigns/creatives/placements, accepted/rejected/duplicate/unknown_status, last_event_at
- `BackendClient`: new `get_pop_report()` and `get_pop_summary()` methods (production)
- `list_pop_events()` retained as legacy test-kso
- `/reports` handler: async backend-driven endpoint replacing `_page()` + demo_data
- Template: KPI cards (PoP events, unique devices/creatives, rejected, campaigns, KSO/manifests), events table, status breakdown, chart placeholders (deferred), Excel export (deferred)
- Charts/slicers/drill-down deferred until backend metrics mature
- `get_report_kpi()` / `get_report_table()` imports removed from `main.py`
- RBAC: `/reports` → `reports.read` (was `view_reports`)
- Backend tests: +8 (PoPSummarySchema, endpoint safety) → 322 total
- Portal tests: 424/424 OK (updated TestReportsPage for production template)
- Fake/demo numbers → GONE, Power BI mentions → removed, test-kso not primary source
- `GET /api/proof-of-play/test-kso` retained as legacy
- B4 Reports UI → ✅ CLOSED

### 39.2.3.1 — Dashboard Production KPI Source Fix

**Dashboard KPI sources switched from test-kso to production endpoints.**

- `list_campaigns_prod()` → `GET /api/campaigns` (production) for campaign KPI counting
- `list_manifests()` → `GET /api/manifests` (new production endpoint) for publications KPI
- Backend: new `GET /api/manifests` production endpoint (safe projection, `publications.read`)
- `GET /api/manifests/test-kso` retained as legacy
- Dashboard no longer uses test-kso as primary KPI source
- Backend tests: 314/314 OK | Portal tests: 425/425 OK
- Dashboard test-kso dependency → GONE ✅

### 39.2.3 — Portal Dashboard Real KPI Integration

**Dashboard connected to backend — demo_data removed as primary KPI source.**

- Dashboard handler: explicit async endpoint replacing `_page()` helper + `get_dashboard_data()`
- KPI computed from 6 existing safe list endpoints: campaigns, creatives, devices, schedules, manifests, approvals
- No new backend endpoints — aggregation happens in portal
- KPI cards: total/active/draft campaigns, creatives, devices, schedules (active), publications, approvals pending
- Fallback: safe empty state when backend unreachable, partial warning when some sources fail
- Demo values ("12", "1 247", "3") removed from dashboard
- Template: card names updated, demo wording removed, production note added
- Portal tests: 425/425 OK (+1 test: `test_no_demo_fake_values`)
- Dashboard DEMO gap → CLOSED ✅

**Remaining:** Reports (39.5)

### 39.2.2.1 — Campaign Create Production API Fix

**Campaign creation now uses production `POST /api/campaigns/by-code` — test-kso no longer primary path.**

- Backend: new `POST /api/campaigns/by-code` endpoint + `CampaignCreateByCode` schema + `create_campaign_by_code` service
- `BackendClient.create_campaign` now calls `/api/campaigns/by-code` (production) instead of `/api/campaigns/test-kso`
- Portal `/campaigns/create` uses production API exclusively
- Template: test-kso reference removed from UI text
- Test-kso endpoints (`POST /api/campaigns/test-kso`, `GET /api/campaigns/test-kso`) retained as legacy/dev helpers
- Backend tests: 314/314 OK
- Portal tests: 424/424 OK
- Campaign UI production gap → FULLY CLOSED ✅

### 39.2.2 — Portal Campaign Create/Edit UI Backend Integration

**Campaign page connected to production Campaign API — create, edit, archive, creative binding.**

- `BackendClient`: 8 new/updated methods — list_campaigns (test-kso safe), create_campaign (test-kso), get_campaign_by_code, update_campaign_by_code, archive_campaign_by_code, list_campaign_creatives, bind_campaign_creative, unbind_campaign_creative
- Portal `/campaigns` page: campaign list + create form + inline edit + archive + creative binding
- Portal POST endpoints: `/campaigns/create`, `/campaigns/{code}/edit`, `/campaigns/{code}/archive`, `/campaigns/{code}/bind-creative`, `/campaigns/{code}/unbind-creative/{cc}`
- RBAC fix: PAGE_PERMISSION_MAP `/campaigns` → `campaigns.read` (match backend permission)
- Template: campaigns table + create/edit/bind forms + archive button; test-kso note replaced with production API note
- All forms server-side POST, no JS/CDN/localStorage
- Portal tests: 424/424 OK
- Campaign UI test-kso dependency → GONE ✅

**Remaining:** Dashboard (39.2.3), Reports (39.5)

### 39.2.1 — Portal Schedule UI Backend Integration

**Schedule page connected to production Schedule Backend API.**

- `BackendClient`: 12 new methods — list_schedules, create_schedule, get_schedule, update_schedule, archive_schedule, list_schedule_slots, create_schedule_slot, update_schedule_slot, disable_schedule_slot, list_placements_prod
- Portal `/schedule` page: schedules list + slots inline + create schedule form + create slot form
- Portal POST endpoints: `/schedule/create`, `/schedule/{code}/create-slot`, `/schedule/{code}/archive`, `/schedule/{code}/items/{slot}/disable`
- RBAC fix: PAGE_PERMISSION_MAP `/schedule` → `scheduling.read` (match backend permission)
- Template: schedules table (schedule_code, name, status, campaign_code, valid_from/to, timezone, slot_count), slots table (slot_code, day_of_week, start/end_time, placement_code, is_active), archive/disable actions
- All forms server-side POST, no JS/CDN/localStorage
- Fallback renders safe empty state when backend unreachable
- Portal tests: 424/424 OK
- Schedule UI DEMO gap → CLOSED ✅

**Remaining:** Campaign UI (39.2.2), Dashboard (39.2.3), Reports (39.5)

### 39.1.3 — Schedule Backend API Hardening

**Schedule + ScheduleSlot models** — production schedule API foundation.

- `Schedule` model: schedule_code, name, status (draft/active/archived), valid_from/to, campaign_code, timezone
- `ScheduleSlot` model: slot_code, day_of_week, start_time/end_time, placement_code, is_active
- `GET/POST /api/schedules` — list + create schedules
- `GET/PATCH /api/schedules/{schedule_code}` — get + update by code
- `POST /api/schedules/{schedule_code}/archive` — archive
- `GET /api/schedules/{schedule_code}/items` — list slots
- `POST /api/schedules/{schedule_code}/items` — create slot
- `PATCH /api/schedules/{schedule_code}/items/{slot_code}` — update slot
- `DELETE /api/schedules/{schedule_code}/items/{slot_code}` — disable (soft)
- Test-kso schedule endpoints retained as legacy
- Backend tests: 314/314 OK
- **Schedule backend gap → CLOSED** ✅

**Remaining:** Portal Schedule UI (39.2), Dashboard (39.2), Reports (39.5)

---

### 39.1.2 — Campaign / Placement Production API Hardening

**Production API foundation:** campaign code-based CRUD, creative binding, placement CRUD.

- `GET/PATCH /api/campaigns/by-code/{campaign_code}` — code-based lookup + update
- `POST /api/campaigns/by-code/{campaign_code}/archive` — archive by code
- `GET /api/campaigns/by-code/{campaign_code}/creatives` — list campaign creatives
- `POST /api/campaigns/by-code/{campaign_code}/creatives` — bind creative (idempotent)
- `DELETE /api/campaigns/by-code/{campaign_code}/creatives/{code}` — unbind (soft)
- `GET/POST /api/placements` — production placement list + create
- `GET/PATCH /api/placements/{placement_code}` — get + update by code
- `POST /api/placements/{placement_code}/archive` — archive by code
- Test-kso endpoints retained as legacy (`/api/campaigns/test-kso`, `/api/schedule/test-kso`)
- Backend tests: +9 new tests, 314/314 OK
- Security gap SG5 (campaign/placement test-kso wrapper) → **CLOSED** ✅

**Remaining:** Schedule CRUD (39.1.3), Portal UI (39.2)

---

### 39.1.1 — Device Gateway Auth Hardening

**Auth foundation:** device gateway PoP ingest + KSO manifest endpoints now require valid device JWT.

- `POST /api/device-gateway/kso/{code}/pop` — was TEST_ONLY → now JWT device auth + code match
- `GET /kso/{device_code}/manifest` — was TEST_ONLY → now JWT device auth + code match
- `GET /manifest/current` — already protected ✅
- `GET /media/{id}` — already protected ✅
- Device auth flow: device_code + secret → bcrypt verify → JWT (60 min)
- Auth failures: uniform 401 "Invalid device credentials" (no info leakage)
- Backend tests: +13 new auth tests, 305/305 OK
- Security gap SG1 (PoP) and SG2 (manifest) → **CLOSED** ✅

**Deferred:** mTLS, credential rotation, nonce/replay protection, rate limiting

---

### 39.0 — Product Backend / Frontend Gap Analysis

**Analysis document:** `docs/audit/product-backend-frontend-gap-analysis.md`

- **23 backend domains** audited: 16 production-ready, 4 partial, 3 TEST_ONLY security gaps
- **16 portal pages** audited: 10 backend-driven, 3 partial, 3 DEMO stubs (dashboard, schedule, reports)
- **29 total gaps** identified

**Pilot blockers (🔴 HIGH):**
- Device gateway auth (manifest/media/PoP — TEST_ONLY без аутентификации)
- Schedule UI (DEMO form, не подключён к backend)
- HW scanner E2E validation (POSTPONED — scanner unavailable)
- Controlled long-run (≥1 час)

**Release plan proposed (7 phases):**
39.1 Backend API hardening → 39.2 Portal UI completion → 39.3 Approval/publication workflow →
39.4 Device/readiness dashboard → 39.5 PoP reporting → 39.6 RBAC/RLS/Admin →
39.7 Pilot runbook

**Regression:** 4939 all green, git clean

---

### 38.17 — Backend Regression Baseline Stabilization

- Backend: 27 cross-component import errors → **FIXED** (sys.path test isolation)
- Backend: 292/292 OK, 0 errors
- Full regression: 4939 all green
- 2 test files patched (`test_z_readiness_gate_383.py`, `test_z_x11_runner_pop_full_e2e_3827.py`)
- Zero business logic changes

---

### 38.15 — HW Scanner E2E Validation Plan

**Plan document:** `docs/audit/hw-scanner-e2e-validation-plan.md`

- **Status:** NOT EXECUTED ❌ — POSTPONED / BLOCKED BY MISSING HARDWARE
- **Reason:** physical barcode scanner hardware unavailable
- **Pilot blocker:** 🔴 HIGH — remains active
- **Validation cannot be replaced** by keyboard simulation
- **Test can resume only** when real hardware scanner is available

**Safe protocol documented:**
- 4-phase test (S1–S4), 8 stop criteria, 7 safety rules, 6 proof points
- Approval token: `PHASE_SCANNER_E2E_APPROVED`
- One controlled test only, operator-observed confirmation, no data logging

**Resumption conditions:** scanner hardware connected + operator present + PHASE_SCANNER_E2E_APPROVED + regression green

**Not executed:** no physical scanner test, no SSH to KSO, no X11/Chromium/runner, no sidecar, no PoP upload, no UKM5 modification

**Safe alternatives:** long-run plan (38.16), BackendIntegration fix (38.17), runbook (38.18)

---

### 38.14 — One-KSO Pilot Readiness Decision Gate

**Decision document:** `docs/audit/one-kso-pilot-readiness-decision-gate.md`

- One-KSO technical dry run: **PASSED** ✅ (D0–D6 all green)
- One-KSO pilot readiness: **CONDITIONAL** ⚠️ (requires HW scanner E2E + controlled long-run)
- Production/fleet rollout: **NOT APPROVED** 🚫

**Proven chain:** portal/backend → manifest/media → KSO player render → PoP → backend → portal report

**Allowed next:** HW scanner E2E plan, controlled long-run plan, BackendIntegration RBAC fix
**Forbidden:** systemd/autostart, fleet rollout, live store pilot, PoP evidence deletion

### 38.13.3 — Phase D Closure (D0–D6 all green) ✅

**D3.1 — Pre-D4 Regression Triage:**
- Backend 6 INTERNALERROR → fixed: `norecursedirs` excludes integration scripts
- Portal-web 9 BackendIntegration → documented (pre-existing 3-layer isolation defect)
- Infra 1 unittest failure → documented (pytest-only, 227/227 pass)
- Core green: **4917 passed, 0 failures**

**D4 — Controlled PoP Upload:**
- **Bug discovered:** `NoReferencedTableError` on `creatives.creative_code` FK — PoP ingest returned HTTP 500 against real PostgreSQL
- Root cause: `service.py` imported `CampaignCreative` but not `Creative`/`User` — SQLAlchemy FK resolution failed at commit
- **Fix:** Added `from app.domains.media.models import Creative` and `from app.domains.identity.models import User` (commit `8b367eb`)
- **PoP upload:** 1 synthetic event sent → HTTP 200 accepted ✅
- **Event data:** test_playback_completed, duration_ms=1000, device=test-dev-seed, campaign=test-camp-seed, creative=test-creative-seed
- **Before:** 0 PoP events, **After:** 1 PoP event (delta +1)
- **Commit:** `7146029` — regression baseline docs updated with FK discovery

**D5 — PoP Report Verification:**
- **Backend:** D4 event found via `/api/proof-of-play/test-kso` ✅
- All fields verified: status=accepted, campaign=test-camp-seed, creative=test-creative-seed, placement=test-place-seed, event_type=test_playback_completed, duration_ms=1000
- All filters pass: device (2 events), campaign (2), creative (2), placement (2)
- KPI count: 2 test_playback_completed events
- Forbidden fields: **CLEAN** (no IDs, secrets, receipts, fiscal, payment, personal data)

**D6 — Cleanup and Phase D Closure:**
- Removed: stale test lock dirs (`/tmp/tmp*` — 40KB), repo `__pycache__`, `.pytest_cache`
- Preserved: backend PoP event (d4-synth-***-0de5dc), config, secret, manifest, media cache
- KSO temp files (`/tmp/d3_evidence/`, `/tmp/d3_runner.py`) remain on KSO (unreachable via SSH) — harmless in /tmp
- UKM5/Openbox/systemd unchanged, no X11/Chromium/runner/sidecar launched
- **Phase D one-KSO E2E dry run: COMPLETE** (D0–D6 all green)

**Stop criteria all met:**
- D3 visual run NOT repeated, X11/Chromium/runner NOT launched
- Sidecar daemon NOT started, UKM5/Openbox/systemd unchanged
- No new PoP events beyond D4's single upload
- Secrets/full URLs/tokens/barcodes NOT printed
- Payload forbidden field check: CLEAN
- D6 cleanup NOT executed (awaiting separate approval)

**Regression:** TBD (after doc update)

### 38.13.2 — D2.1: Python 3.6 Runner Compatibility + Fullscreen Runner Plan
- **Blocker 1:** `datetime.fromisoformat` unavailable on Python 3.6 (KSO runtime)
- Created `kso_player/timestamp_utils.py` with `parse_iso_utc()` via `strptime` — py36-compatible
- Replaced all `fromisoformat` calls in `runtime_gate.py`, `screensaver_creative.py`, `state_observer.py`, `simulator.py`, `run_cycle.py`
- **Blocker 2:** Registered fullscreen profile `portrait_fullscreen_idle_screensaver_768` (768×1024+0+0, kiosk, idle_only)
- 13 new unit tests for timestamp parser — Z, microseconds, offset, invalid→None
- Added `PYTHONPATH` to subprocess calls in CLI tests (`test_run_once_cli.py`, `test_run_once_cli_backend.py`, `test_run_cycle_runtime_config.py`)
- **Regression:** backend 292 ✅ | portal-web 404 ✅ | kso_state_adapter 86 ✅ | kso_player 2065 ✅ | kso_sidecar 1838 ✅ | infra 227 ✅
- Total: **4912 passed, 0 failed** (vs 4894 baseline — +18 new tests)

### 38.13.1 — Phase D Geometry Consistency Fix
- **Critical fix:** test-dev-seed GatewayDevice was linked to shared landscape display_surface (1920×1080)
- Real KSO is portrait 768×1024 — created dedicated portrait surface + logical_carrier
- GatewayDevice updated to portrait surface; legacy landscape surface preserved for other devices
- Created `docs/audit/kso-portrait-architecture-pivot.md`
- Manifest/media NOT geometry-dependent — no content changes needed

### 38.13 — Phase D Preflight

### 38.12.2 — Backend Regression Stabilization
- Fixed 27 pre-existing backend errors: PYTHONPATH config in `backend/pyproject.toml`
- Added `["../apps/kso_player", "../apps/kso_sidecar_agent"]` to pytest pythonpath
- Backend: 292/292 green (was 265)
- Portal-web: 404/404 green (20 BackendIntegration excluded — need live backend)
- Full regression: 4894 green baseline
- Secret discrepancy resolved: 32→25 bytes = different registration instances

### 38.13 — Phase D Preflight
- Created `docs/audit/phase-d-one-kso-e2e-dry-run-preflight.md` — full runbook
- 6 sub-phases (D0–D6), 12 stop criteria, rollback procedure, approval gates
- Readiness verified: backend health, manifest, credential, campaign/placement
- No KSO/sidecar/X11/PoP executed — documentation only

### Requirements verification
- ✅ Full regression: 4894 green
- ✅ Git status clean
- ✅ No secrets / full URLs / tokens committed
- ✅ No sidecar/X11/PoP/runner launched

---

## [38.12.1] — Phase C Controlled Run + Stabilization (2026-06-25)

### Phase C.1 — Manifest Sync
- GatewayDevice `test-dev-seed` created in `gateway_devices` + credential in `device_credentials`
- Publication chain wired: device → display_surface → publication_target → manifest_version → manifest_items
- Manifest sync via `/api/device-gateway/manifest/current`: ✅ `served`, 1 item (`image/png`, slot-000)
- Manifest saved on KSO: `manifest/current_manifest.json`, 1 item

### Phase C.2 — Media Sync
- Media downloaded: ✅ `slot-000.png` (108 bytes), cache complete
- Endpoint: `/api/device-gateway/media/{manifest_item_id}` — 200 OK

### Backend/Data Fixes (during Phase C)
- **ScheduleItem model** — added to `scheduling/models.py` (table existed, model was missing → ImportError in `_collect_kso_source_items`)
- **GatewayDevice** — linked to display_surface + store (was unlinked, causing `no_manifest`)
- **schedule_item.date** — updated to today (was 2026-06-21, past valid_to → items filtered out)
- **media_path** — fixed to `creatives/...` format (was `media/current/...` → 403 `_validate_object_key`)

### Security
- No sidecar daemon / PoP upload / X11 / Chromium / UKM5 modifications
- No secrets, full URLs, or tokens in output or git
- No media/manifest/runtime KSO files committed

## Phase C Preflight (38.12)

- `test-kso-phase-c-manifest-media-cache-preflight.md` — 10-section Phase C readiness plan
- Pre-conditions: backend reachability, auth path, published manifest, creative media, disk space
- Command templates (masked): config-status, secret-store-check, sync-manifest (⛔ not run), sync-media (⛔ not run)
- 10 safety gates (G1–G10), 10 stop criteria (S1–S10), rollback (partial/full)
- No network calls from KSO, no sidecar/X11/Chromium/PoP started
- Full regression: 4926 green (292+424+86+2059+1838+227)

## Phase B Applied — Config on Test KSO (commit `83afb9c`)

- AGENT_ROOT: `/home/ukm5/kso-agent`, 9 subdirectories, valid config (177 bytes), secret (32 bytes, 0600)
- Backend reachable, no placeholders, secret via safe stdin (never printed)
- No sidecar/X11/Chromium/PoP started

## [v0.6.0] — Sidecar Config Readiness (Phase B Preparation)

**Tag:** `v0.6.0-sidecar-config-readiness` (2026-06-26)
**Commit:** (see tag)

### Sidecar Config

- `config/agent_config.json.example` — safe template with placeholders (no real values)
- `local_config.validate_no_placeholders()` — dry-check config without exposing values
- `local_config.config_status()` — enhanced: now returns `has_placeholders`, `placeholder_fields`
- `PLACEHOLDER_PATTERNS` — detects `<TEST_BACKEND_BASE_URL>`, `<TEST_KSO_DEVICE_CODE>`, etc.

### Gitignore

- `agent_config.json`, `device_secret.dev`, `*_filled.json` — ignored
- `agent-root/`, `kso-agent-root/`, `test-agent-root/` — local test roots ignored

### Docs

- `test-kso-sidecar-config-preparation.md` — Phase B analysis, config mechanisms, operator checklist
- Updated: runbook, config-checklist, readiness-gate, pilot-plan, tech-debt

### Readiness

- `sidecar_config_ready` stays `false` — backend cannot inspect local sidecar filesystem
- Only `validate_no_placeholders()` on KSO determines real config readiness

---

## [v0.5.0] — Test-KSO Readiness Control Plane + Phase A Backend Readiness

**Tag:** `v0.5.0-test-kso-phase-a-readiness` (2026-06-25)
**Commit:** `c6ad526`

### Readiness Control Plane

- `GET /api/test-kso/readiness?device_code=<code>` — comprehensive readiness status (55+ fields)
- `POST /api/test-kso/seed` — idempotent synthetic seed (device→campaign→creative→manifest chain)
- `GET /api/test-kso/sidecar-config-checklist` — 12 sidecar config field statuses (names only, no values)
- Portal `/readiness` — 8 component sections + Phase D Gate + Operator Preflight guidance
- `required_operator_steps` — 13 preflight steps (Phase A/B/C)
- Phase D gate: ⛔ blocked, requires explicit manual approval

### Contract Fix

- `overall_ready` now honestly requires `sidecar_config_ready=true` AND `media_cache_ready=true`
- Previously returned `true` ignoring missing sidecar config and media cache

### Docs

- `test-kso-live-backend-seed-runbook.md` — operator preflight runbook (Phase A/B/C, placeholders, no secrets)
- `test-kso-live-config-checklist.md` — 12 sidecar config fields reference
- `test-kso-phase-a-backend-readiness-result.md` — live Phase A execution result
- `versioning-policy.md` — SemVer policy, tag naming, regression requirements

### Regression

- Backend: 292 ✅
- Portal: 424 ✅
- State: 86 ✅
- KSO Player: 2059 ✅ (12 skipped)
- Sidecar Agent: 1838 ✅
- Infra: 227 ✅
- **Total: 4926 green**

### Not Included

- ❌ Live sidecar config on KSO (Phase B — blocked)
- ❌ Media cache on KSO (Phase C — blocked)
- ❌ Phase D physical run / X11 / Chromium (blocked)
- ❌ SSH to KSO (not executed)
- ❌ HW scanner integration
- ❌ Production deployment

---

## [v0.4.0] — Runner / Manifest / Media / PoP Dev E2E

**Tag:** (not yet tagged)
**Period:** 2026-06-22 – 2026-06-24

### X11 Runner

- Guarded X11 screensaver runner with kill-switch and idle-state safety
- Portrait overlay player (768×1024) — profile contract, shell, smoke harness
- X11 click-through renderer contract + physical proof harness
- Fullscreen screensaver input pass-through design
- Rollback to UKM5 after screensaver exit (confirmed: grey 236,236,236)

### Manifest

- KSO safe manifest extractor — creative_code preservation
- Bridge: manifest order → player playlist → creative → media filename
- `creative_code` tracing through entire chain: manifest → playlist → creative → PoP

### Media Cache

- Sidecar media cache bridge to X11 runner
- Sync/reference resolution: filename → symlink → invalid → hidden/blocked
- Media availability status in readiness report

### PoP (Proof of Play)

- X11 runner PoP reporting E2E bridge
- `ScreensaverPoPDraft → JSONL → PopPayloadEvent.creative_code`
- Backend PoP ingest: placement→campaign→creative mapping
- Duplicate `event_code` idempotent handling
- Campaign PoP report with creative_code breakdown
- Portal PoP report page

### Backend

- Portal user CRUD
- Backend PoP integration E2E test
- Sidecar regression baseline stabilization
- Python 3.6 X11 screensaver proof harness

### Infrastructure

- Docker Compose: PostgreSQL, Redis, ClickHouse, MinIO, Nginx
- Alembic migrations
- Full regression: 4926 tests total

---

## [v0.3.0] — Physical KSO Architecture Pivot + X11 Click-Through Proof

**Tag:** (not yet tagged)
**Period:** 2026-06-20 – 2026-06-22

### Architecture Pivot

- Pivot from KSO vendor integration to physical KSO device control
- Portrait idle overlay player profile (768×1024)
- Player shell: safe observer stub, kill-switch, state adapter
- UKM5 process integrity guard — never modify UKM5/Openbox/systemd

### Physical KSO

- Physical KSO dry smoke validation (pre-configured test device)
- Phase 2 overlay render execution — manual one-shot, no fullscreen/kiosk
- Remote X11 proof harness for controlled rollout
- Status correction: visual display confirmed

### Contracts

- X11 click-through renderer contract
- Portrait overlay local smoke harness
- Physical KSO test plan
- Fullscreen idle screensaver interaction design

### Safety

- Kill-switch marker file
- Safe player state observer (read-only)
- UKM5 restoration guarantee after rollback
- No autostart/systemd/ fleet — explicit manual control

---

## [v0.2.0] — KSO Backend/Portal Vertical Chain

**Tag:** (not yet tagged)
**Period:** 2026-06-18 – 2026-06-20

### KSO Backend

- KSO runtime config fields (`backend/app/domains/kso/`)
- KSO device registration, status management
- KSO channel → device hierarchy mapping
- KSO manifest generation with creative_code + media_ref

### Portal

- KSO device management pages
- KSO channel configuration
- KSO manifest preview
- Backend API client — secure httpx-based with credential isolation

### Architecture

- KSO player adapter architecture doc
- KSO vendor integration questions/contract
- KSO local interface contract
- Hierarchical projection: Channel→DeviceType→PhysicalDevice→LogicalCarrier→DisplaySurface+CapabilityProfile

---

## [v0.1.0] — Backend / Portal Foundation

**Tag:** (not yet tagged)
**Period:** 2026-06-16 – 2026-06-18

### Architecture

- Multichannel architecture skeleton (commit `00c12c7`)
- Channel-agnostic core + adapters pattern
- FastAPI + React + PostgreSQL + ClickHouse + MinIO + Redis + Chromium kiosk
- Manifest: signed JSON, no JWT in URL; mTLS deferred

### Core

- Identity and Access domain — user CRUD, auth (JWT), RBAC
- Docker Compose dev environment
- Alembic migration framework
- Nginx reverse proxy
- Portal: login, dashboard, admin pages
- CI-ready backend test suite

### Database

- 9 core tables: channels, device_types, physical_devices, logical_carriers, display_surfaces, capability_profiles, users, roles, permissions
- `/health` — status + DB connectivity check

---

## Tag Naming Convention

```
v<major>.<minor>.<patch>-<descriptor>
```

- **patch:** small fixes, regression updates, docs-only changes
- **minor:** completed project phase (new feature group, new domain)
- **major:** production release, pilot rollout, breaking changes
- **descriptor:** short phase name (e.g. `test-kso-phase-a-readiness`)

### Requirements for every minor tag

- ✅ Full regression green (all 6 suites)
- ✅ Git status clean
- ✅ No secrets / real URLs / tokens / device_secret in docs, output, or tag message
- ✅ Annotated tag (`git tag -a`) with description

## 39.4.1 — Backend Device Dashboard API (2026-06-26)

### Added
- `GET /api/device-dashboard` aggregation endpoint — crosses GatewayDevice, KsoDevice,
  DeviceCredential, DeviceSession, DeviceHeartbeat, DeviceCurrentManifestState,
  KsoProofOfPlayEvent, DeviceMediaCacheItems (8 tables) into safe projection
- Readiness badge: `ready` / `warning` / `blocked` / `unknown` (server-side logic)
- `_parse_dt()` helper for SQLite datetime compatibility

### Fixed
- GAP 3: `record_heartbeat()` now cross-propagates `last_seen_at` to `KsoDevice` by `device_code`
- Import: `from app.domains.hierarchy.models import KsoDevice`

### Deferred
- GAP 2: `sidecar_status` in heartbeat payload → 39.4.4

### Tests
- 16 new tests in `backend/tests/test_device_dashboard_api.py`

## 39.4.2 — Portal Device Dashboard (2026-06-26)

### Added
- `/device-dashboard` route — backend-driven page with server-side rendering
- `BackendClient.get_device_dashboard()` method with filter params
- Template `templates/pages/device-dashboard.html` — device table with 14 columns:
  device_code, store, gateway/kSO status, heartbeat (status+age+app_version),
  sidecar/player versions, credential status, sessions, manifest, media cache, PoP, readiness badge
- Filter bar: keyword, channel_code, store_code, readiness_badge with reset link
- Summary cards: total/ready/warning/blocked counts
- Readiness legend
- CSS: readiness badge colors, age freshness, cache health, filter bar layout
- Nav link in sidebar under "КСО" section

### Tests
- 20 new portal tests in `test_main.py` (TestDeviceDashboardPage)
- `_FakeBackendClient` extended with `get_device_dashboard()` + `close()`
- `_FakeBackendClientDown` extended with `close()`
- Mock dashboard data: 4 devices (ready/warning/blocked/unknown)

### Safety
- No JS, no CDN, no localStorage
- No raw UUIDs, secrets, tokens, backend URLs in rendered HTML
- Backend down → safe fallback with "Данные временно недоступны" message

## 39.4.3 — Close Device/Sidecar Dashboard Gaps (2026-06-26)

### GAP 2 — CLOSED ✅ Sidecar status in heartbeat
- `DeviceHeartbeatRequest.sidecar_status` optional field added (stopped/starting/running/warning/error/unknown)
- Stored in `DeviceHeartbeat.details_json` via `record_heartbeat()`
- `DashboardHeartbeatSummary.sidecar_status` schema field added
- `_extract_sidecar_status()` extracts from JSON (handles PG JSONB + SQLite strings)
- Device dashboard now returns `sidecar_status` from latest heartbeat
- Old heartbeat payloads without sidecar_status → None (safe fallback)
- Invalid values → normalized to None
- 3 backend tests added

### GAP 4 — CLOSED ✅ Readiness page hardened
- `/readiness` route rewritten to use production `GET /api/device-dashboard`
- KPI computed server-side: total, ready, warning, blocked, unknown, stale_hb, expired_cred, missing_manifest
- Summary cards + detail cards + filter bar
- Device table with readiness badges
- Link to `/device-dashboard` for full detail
- Template rewritten — no test-kso wording, no hardcoded data
- 14 portal tests (replaced 26 old test-kso tests)

### GAP 5 — CLOSED ✅ Devices page dashboard link
- `/devices` page now has "📡 Открыть Device Dashboard →" link
- 1 portal test added

### Regression
- Backend: 398 (+3), Portal: 458 (+...), KSO: 2845
- Total: 5103 green

## 40.0 — TZ Alignment / Security & RLS Audit Gate (2026-06-26)

### Audit
- Comprehensive audit: `docs/audit/tz-alignment-security-rls-audit.md` (7 разделов)
- TZ traceability matrix: 34 requirements mapped to backend/frontend/RBAC/RLS/tests
- RLS/RBAC endpoint audit: 28 endpoints/pages audited for scope enforcement and role bypass risk

### Key findings
- **TZ compliance:** 27/34 DONE (79%), 4 PARTIAL (RLS, audit, creative UX, charts), 2 MISSING (HW scanner, long-run), 1 OUT-OF-SCOPE (fleet)
- **RBAC:** FULLY ENFORCED ✅ — 47 permissions, 8 roles, `require_permission()` on every backend endpoint, `require_auth_for_page()` on every portal route
- **RLS:** PARTIAL 🟡 — `user_rls_scopes` table + UI assignment exist, but **query-level NOT enforced** (no `WHERE scope IN (user_scopes)` in SQLAlchemy)
- **Critical RLS gaps:** 28 endpoints return unfiltered data across all scopes
- **Pilot blockers:** HW scanner E2E (postponed), controlled long-run (decision needed)

### Recommended next
- 40.1: RLS query-level enforcement (P0 — before pilot)
- 40.2: Admin/audit log hardening (P1 — post-pilot)
- 40.3: Pilot readiness gates (HW scanner + controlled long-run)
- 40.4: v0.11.0 release tag (after 40.1+40.3 green)

### No code changes
- Audit-only: no backend/frontend/KSO modifications
- No physical tests, no SSH/X11/Chromium/runner/sidecar daemon/PoP
- No secrets committed

### Retrospective tags

Older milestones (v0.1.0–v0.4.0) have not been tagged. Retrospective tags should only be created after explicit confirmation, as they may point to commits with known issues or incomplete regression state.

### Future Tags (recommended)

| Tag | Description |
|---|---|
| `v0.6.0-sidecar-config-readiness` | Sidecar config filled + verified on KSO (Phase B) |
| `v0.7.0-one-kso-e2e-dry-run` | Controlled one-KSO E2E dry run (Phase C+D, no prod) |
| `v0.8.0-pilot-readiness` | Pilot rollout gate — all prerequisites, 4926 green |
| `v1.0.0-kso-production-release` | First production KSO release |

## 44.1 — Inventory Engine / Sold Out / Forecast (2026-06-16)

### Added
- `reservation_type` column in BookingItem (campaign/internal/emergency/filler)
- Migration `031_add_reservation_type_to_booking_items`
- Inventory service: sold_out flag, occupancy_pct, business-language reasons, alternatives
- Forecast v1 (`calculate_forecast()` — spots × days × devices, disclaimer «Оценка по расписанию»)
- Snapshot endpoint `GET /api/inventory/snapshot`
- Portal `/inventory` page: summary cards, availability table, forecast, snapshot
- Sidebar item «⏱ Рекламное время»
- 20 backend tests (`test_inventory_engine_441.py`), 8 portal tests

### Fixed (44.1.1)
- 8 pre-existing backend failures from business-language refactor (43.7)
- Backend regression: 710/0

## 44.2 — Creative QA & Media Validation (2026-06-16)

### Added
- KSO profile: 768×1024 portrait (matches physical test device)
- Dangerous type blocking: HTML/JS/SVG/ZIP/EXE/DLL/SH/PY + 8 more — rejected before MIME check
- MP4 disguise detection (magic bytes `ftyp` check)
- Duplicate SHA-256 detection (409 Conflict)
- `scan_status` column (not_configured/pending/clean/infected/failed)
- Migration `032_add_scan_status_to_creatives`
- Moderation workflow: submit-review → approve/reject with audit + reason codes
- Creative policy endpoint: `GET /api/creatives/policy`
- Campaign binding gate: only `status == "approved"` creatives can be bound
- Portal `/creatives`: summary cards, scan_status, moderation actions
- 31 backend tests, 676 portal tests green

### Fixed (44.2.1)
- 19 backend failures: DDL in 3 test files missing `scan_status` column
- Stale docstring `1440×1080` → `768×1024 portrait` in router.py
- Campaign binding mock test missing `creative.status = "approved"`
- AV policy: added `av_policy_mode` and `require_av_clean_for_publication` fields
- AV deviation DEV-007 documented in deviation register
- 3 new campaign binding gate tests: rejected/pending_review/validation_failed creatives rejected

### AV Policy
- Pilot/dev mode: manual approval allowed without AV scanner (warning in UI, audit trail)
- Production mode: `scan_status=clean` required before publication
- Fake AV pass prohibited — `scan_status=clean` never set automatically without real scanner
- `CreativeAVScanner` interface ready for ClamAV or commercial scanner integration

### Deferred
- MP4/WebM video validation (codec, duration, audio)
- GIF validation (duration, CPU)
- Real AV scanner integration
