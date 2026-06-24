# Test KSO Technical Validation → Pilot Rollout Plan

> **Статус:** 📋 Audit / Roadmap
>
> Дата: 2026-06-16
> Шаг: 37.12
> Ревизия: 5 (38.0.4 — safe zone mapping)
>
> **ВАЖНО:** Этот документ планирует два последовательных этапа:
> 1. **Test KSO technical validation** — проверка цепочки на 1 КСО (текущий фокус)
> 2. **Pilot rollout** — развёртывание на группе КСО/магазинов (отдельный следующий этап)
>
> **Portrait Player Design (38.0.5):** Profile `portrait_idle_overlay_768`.
> Overlay zone y=400-640 (768×240), creative canvas 768×200 centered.
> См. `docs/audit/portrait-player-profile-design.md`.

## Target Scenario

**Test KSO:** установить runtime на 1 КСО, загрузить через портал synthetic креатив, создать кампанию, назначить расписание, опубликовать manifest, проверить smoke player/sidecar, отправить PoP, увидеть PoP в портале.

**Pilot rollout (следующий этап):** развернуть на 3–5 КСО в 2–3 магазинах, реальный Chromium kiosk, реальный UKM4, production auth, media delivery, 24–72ч стабильности.

**Целевое оборудование:** ServPlus Sherman-J 5.1 (Linux), СуперМаг УКМ 5, Chromium kiosk.

**Фактический fleet (38.0.3-pivot):** вся сеть — 768×1024 портрет, УКМ5 fullscreen kiosk.
KSO Player landscape (1920×1080) снят как v1 target. Новый v1 target: **portrait 768×1024 UKM5-compatible player profile**.

**Pilot rollout (будущее):** portrait player на 3–5 КСО, production auth, 24–72ч стабильности.
Landscape player сохранён для будущих ландшафтных КСО (если появятся).

---

## End-to-End Pilot Chain (24 Steps)

| # | Шаг | Статус | Модуль | Что есть | Что нужно | Блокер? |
|---|---|---|---|---|---|---|
| 1 | Создать пользователя в портале | DEMO_ONLY | portal-web | Admin page с таблицей, demo users, кнопка disabled | Backend user CRUD + portal API integration | ✅ P0 |
| 2 | Назначить роль | DEMO_ONLY | portal-web + backend | Admin role grid, contract | Backend role assignment + enforcement | ✅ P0 |
| 3 | Войти в портал | DEMO_ONLY | portal-web + backend | Login/logout placeholders (disabled) | Session/JWT + local auth | ✅ P0 |
| 4 | Завести магазин | DEMO_ONLY | portal-web + backend | Organization domain, Stores page DEMO | Portal→backend API + real data entry | ❌ |
| 5 | Завести КСО | DEMO_ONLY | portal-web + backend | Device operations domain, Devices page DEMO | Portal→backend API + device registry | ❌ |
| 6 | Установить runtime package на КСО | DONE | infra/kso-linux | Bootstrap, preflight, release builder, systemd × 3 | Реальное железо | ❌ |
| 7 | Настроить state adapter | DONE | kso_state_adapter | Daemon, file source, systemd | Реальный UKM4 source / static fallback | ❌ |
| 8 | Настроить sidecar | DONE | kso_sidecar_agent | Daemon, pull model, auth, heartbeat | Реальные backend URL + device credential | ❌ |
| 9 | Запустить player | DONE | kso_player | Daemon, loop, cycle, shell snapshot | Реальный Chromium kiosk | ❌ |
| 10 | Загрузить креатив через портал | MISSING | portal-web + backend | Creatives page DEMO, media domain models | Upload UI + API + storage pipeline | ✅ P0 |
| 11 | Провалидировать креатив | MISSING | backend/media | Media domain (models), KSO requirements в UI | Validation logic (1440×1080, PNG/JPEG, no audio) | ❌ |
| 12 | Создать кампанию | DEMO_ONLY | portal-web + backend | Campaigns page DEMO, campaign domain models | Portal→backend CRUD API | ❌ |
| 13 | Назначить расписание | DEMO_ONLY | portal-web + backend | Schedule page DEMO, scheduling domain models | Portal→backend CRUD API | ❌ |
| 14 | Отправить на согласование | DEMO_ONLY | portal-web + backend | Approvals page DEMO, orchestrator domain (empty) | Workflow engine | ❌ |
| 15 | Утвердить | DEMO_ONLY | portal-web + backend | Maker-checker в contract | Approval workflow backend | ❌ |
| 16 | Сформировать manifest | ✅ DONE | backend/manifests | Manifest generation + safe projection (37.7) | ✅ | ❌ |
| 17 | Опубликовать manifest | ✅ DONE | backend/manifests + portal-web | Publish endpoint + portal UI (37.8) | ✅ | ❌ |
| 18 | Sidecar забирает manifest | ✅ DONE | kso_sidecar_agent + device_gateway | Device gateway KSO endpoint + sidecar extractor smoke (37.9) | ✅ | ❌ |
| 19 | Player показывает креатив | DONE (tests) | kso_player | Display cycle, playlist, render plan | Реальный Chromium + manifest + media | ❌ |
| 20 | Player создаёт PoP | DONE (tests) | kso_player | PoP writer, JSONL events | Реальный playback | ❌ |
| 21 | Sidecar отправляет PoP | DONE (tests) | kso_sidecar_agent | PoP pickup, batch, send, rotation | Реальный backend URL | ❌ |
||| 22 | Backend принимает PoP | ✅ DONE (37.10) | backend/proof_of_play | PoP ingest + safe correlation chain | Portal reports ✅ DONE (37.11) | ❌ |
|| 23 | Portal показывает отчёт | ✅ DONE (37.11) | portal-web + backend | Backend-driven PoP view + filters + safe KPI | — | ❌ |
| 24 | Excel export готовит выгрузку | MISSING | portal-web + backend | Export block disabled, RLS note | Real Excel generation + RLS filters | ❌ |

### Сводка по цепочке

| Статус | Шагов |
|---|---|
| ✅ DONE (в тестах) | 8 (6, 7, 8, 9, 18, 19, 20, 21, 22) |
| 🟡 PARTIAL | 1 (16) |
| 🟠 DEMO_ONLY | 12 |
| 🔴 MISSING | 2 (10, 24) |
| 🚫 BLOCKER (P0) | 5 (1, 2, 3, 10, 23) |

**Без P0-блокеров пилот невозможен.** Остальные шаги — PARTIAL/DEMO/DONE — доводятся в рамках интеграции.

---

## Readiness Checklist

### Critical Path (MUST HAVE)

| # | Элемент | Статус | Владелец |
|---|---|---|---|
| CP1 | Auth session/JWT для portal | ❌ MISSING | Backend |
| CP2 | Local user CRUD (create, role, status) | ❌ MISSING | Backend + Portal |
| CP3 | Portal→backend API client | ❌ MISSING | Portal |
| CP4 | Creative upload (UI + storage) | ❌ MISSING | Backend + Portal |
| CP5 | Campaign create workflow | ❌ MISSING | Backend + Portal |
| CP6 | Manifest generation trigger | 🟡 PARTIAL | Backend |
| CP7 | PoP ingest → portal reports | ✅ DONE (37.10 + 37.11) | Backend + Portal |
| CP8 | KSO runtime deployed on real HW | 🟡 READY (docs) | Infra |

### Nice-to-Have (for pilot)

| # | Элемент | Статус |
|---|---|---|
| NH1 | Approval workflow (можно без maker-checker для пилота) | 🟠 DEMO |
| NH2 | Schedule inventory conflict detection | 🟠 DEMO |
| NH3 | Excel export | 🔴 MISSING |
| NH4 | MFA для admin | 🔴 MISSING |
| NH5 | BI drill-down | 🟠 DEMO |

---

## Blockers to Resolve (Priority Order)

| # | Блокер | Зависимости | Оценка |
|---|---|---|---|
| B1 | Auth session/JWT + login | Identity domain, security.py | 3-5 шагов |
| B2 | Portal→backend API client | OpenAPI contract, HTTP client | 2-3 шага |
| B3 | User CRUD (portal) | B1, B2 | 2-3 шага |
| B4 | Hierarchy: 1 филиал + 1 магазин + 1 КСО | B1, B2, organization domain | 2-3 шага |
| B5 | Creative upload pipeline | B1, B2, media domain | 3-5 шагов |
| B6 | Campaign → schedule → publication | B1, B2, B4, B5 | 5-8 шагов |
| B7 | Manifest E2E | B2, B6, publications domain | 2-3 шага |
| B8 | PoP E2E (player→sidecar→backend→portal) | B2, B7 | 3-5 шагов |
| B9 | Real HW deployment | B4, infra готово | 1 день |

---

## Minimum Implementation Sequence

### Phase 1 — Архитектурное выравнивание и API Contracts

**Результат:** OpenAPI spec portal↔backend, подтверждённый архитектором.

**Блокеры:** нет (design-only).

**Commit:** `docs/api/portal-backend-openapi.yaml`

**Тесты:** проверка валидности OpenAPI schema.

**Критерий:** архитектор утвердил API контракт.

---

### Phase 2 — Auth / Session / User CRUD / RBAC / RLS Backend

**Результат:** можно создать пользователя, назначить роль, войти в портал, backend проверяет permissions и RLS.

**Блокеры решаются:** B1, B2, B3.

**Документ:** `docs/backend/auth-user-rbac-rls-architecture.md`

**Декомпозиция:**

#### Шаг 36.2 — Auth/User/RBAC/RLS Architecture Contract ✅

Настоящий документ. Описывает целевую модель:
- Локальная авторизация + будущий SSO/AD
- Password policy (bcrypt, 8-128 символов, 5 попыток)
- Session model (JWT + refresh token rotation)
- RBAC enforcement (permission check middleware)
- RLS enforcement (scopes → SQLAlchemy filters)
- Будущие таблицы: user_rls_scopes, login_audit_events, admin_audit_events, mfa_settings
- Будущие API endpoints: /api/auth/*, /api/users, /api/roles, /api/admin/audit
- Forbidden fields, log safety, admin safety

#### Шаг 36.3 — Auth DB Model and Migrations

- Alembic миграция для новых таблиц: `user_rls_scopes`, `login_audit_events`, `admin_audit_events`, `mfa_settings`
- Обновление `users`: `is_archived`, `archived_at`, `archived_by`
- Индексы согласно контракту
- Seed-обновление: начальные RLS scopes для admin

#### Шаг 36.4 — Password Hashing / Session Foundation

- `hash_password()` / `verify_password()` — bcrypt через passlib
- `create_access_token()` / `create_refresh_token()` — JWT с PyJWT
- `get_current_user()` dependency — извлекает пользователя из JWT
- `check_permission(required)` dependency — проверяет permission
- Session lifecycle: login → access + refresh → refresh rotation → logout → revocation

#### Шаг 36.5 — User CRUD Backend

- `POST /api/auth/login` — вход с audit
- `POST /api/auth/logout` — выход с revoke
- `POST /api/auth/refresh` — обновление токенов
- `GET /api/auth/me` — текущий пользователь
- `GET /api/users` — список (admin)
- `POST /api/users` — создание (admin)
- `PATCH /api/users/{username}/status` — блокировка/архивирование (admin)
- Rate limiting на login (5 попыток)
- Все forbidden fields исключены из ответов

#### Шаг 36.6 — Admin Users API + Portal Integration

- `GET /api/roles` — список ролей
- `POST /api/users/{username}/roles` — назначение ролей (admin)
- `POST /api/users/{username}/rls-scopes` — назначение RLS (admin)
- `GET /api/admin/audit` — журнал аудита (admin)
- Portal API client (httpx) для вызова backend
- Portal login page: функциональная форма, обработка ошибок
- Portal header: отображение текущего пользователя
- Portal page guards: redirect на /login если не auth

#### Шаг 36.7 — RBAC/RLS Enforcement Tests

- Unit: JWT generation/validation
- Unit: bcrypt hash/verify
- Integration: login → session → protected endpoint
- Integration: permission check → 403
- Integration: RLS filter → filtered results
- Portal: login page функциональна
- Portal: страницы недоступны без auth
- Security: forbidden fields не в ответах
- Security: device_service не может войти через /login
- Security: admin auditor changes

**Что должно быть в commit (суммарно 36.3–36.7):**
- `backend/alembic/versions/023_auth_rbac_rls.py` — миграция
- `backend/app/domains/identity/` — обновлённые модели, router, service, schemas
- `backend/app/core/security.py` — JWT + bcrypt + deps
- `backend/app/core/deps.py` — get_current_user, check_permission
- `backend/app/domains/identity/seed.py` — обновлён
- `apps/portal-web/` — API client, обновлён login/logout/admin

**Тесты (суммарно 36.3–36.7):**
- Auth flow (login, refresh, logout, session expiry)
- JWT validation, refresh rotation
- Password hashing (bcrypt verify, reject wrong)
- Rate limiting (5 попыток → lock)
- Permission check (allow/deny per endpoint)
- RLS filter (scoped queries)
- Portal login/logout функциональность
- Security: forbidden fields audit

**Критерий готовности:**
- Пользователь создаётся через API
- Пользователь входит через portal login
- Backend проверяет permission на каждом запросе
- RLS фильтрует данные до pagination/aggregation
- Нет доступа к страницам без auth
- device_service заблокирован от portal login
- Все изменения аудируются
- Все forbidden fields исключены

---

### Phase 3 — Hierarchy + Device Registry for 1 KSO

**Результат:** в системе есть 1 реальный филиал, 1 магазин, 1 КСО.

**Блокеры решаются:** B4.

**Что должно быть в commit:**
- Portal stores page → реальные данные из backend API
- Portal devices page → реальные данные из backend API
- Seed или ручной ввод 1 филиала + 1 магазина + 1 КСО
- Device credential для sidecar

**Тесты:**
- Organization CRUD через API
- Device registration с credential
- Portal отображает реальные (не DEMO) данные

**Критерий готовности:**
- В портале виден 1 реальный магазин и 1 КСО
- Device credential создан и сохранён

---

### Phase 4 — Creative Upload + Validation + Storage

**Результат:** можно загрузить PNG/JPEG 1440×1080 через портал.

**Блокеры решаются:** B5.

**Что должно быть в commit:**
- Portal creative upload form (не disabled)
- Backend media upload endpoint
- Validation: размер, формат, длительность, no audio
- Storage: локально или MinIO (как настроено)

**Тесты:**
- Upload валидного PNG → accepted
- Upload невалидного (не тот размер, формат) → rejected
- Upload аудио → rejected
- Portal creatives page показывает загруженные креативы

**Критерий готовности:**
- Креатив 1440×1080 PNG загружен через портал
- Отображается в creatives library

---

### Phase 5 — Campaign / Schedule / Approval / Publication

**Результат:** можно создать кампанию, назначить расписание, отправить на согласование, утвердить, опубликовать.

**Блокеры решаются:** B6.

**Что должно быть в commit:**
- Portal campaign create form
- Portal schedule assignment UI
- Backend campaign/schedule CRUD endpoints
- Backend approval workflow (упрощённый — 1 шаг для пилота)
- Backend publication trigger → manifest generation

**Тесты:**
- Campaign CRUD через API
- Schedule assignment с валидацией слотов
- Approval flow (create → submit → approve)
- Publication → manifest generated

**Критерий готовности:**
- Кампания создана, расписание назначено, manifest сгенерирован
- Manifest доступен для sidecar pull

---

### Phase 6 — Manifest E2E Generation ✅ (37.7, 37.8, 37.9)

**Результат:** manifest generation → publish → device gateway endpoint → sidecar-compatible fetch.

**Блокеры:** B7 закрыт.

**Что сделано:**
- Backend manifests domain: GeneratedManifest модель, генерация из approved placement через safe projection
- Publish endpoint: generated → published transition (idempotent)
- Device gateway KSO endpoint: `GET /api/device-gateway/kso/{device_code}/manifest` (TEST_ONLY)
- Sidecar extractor smoke: published manifest wrapper совместим с существующим extractor
- Player local smoke: sidecar-produced manifest читается player без изменений runtime

**Тесты:**
- Backend: 13 unit-тестов manifest domain (схемы, сервис, safe response)
- Sidecar extractor: 671 тест (gateway response → safe extract)
- E2E local delivery smoke: 14 тестов (sync → playlist → render plan → shell snapshot)
- Все 3664 теста проходят

**Критерий готовности:**
- ✅ Manifest генерируется из approved placement
- ✅ Manifest публикуется (generated → published)
- ✅ Device gateway отдаёт sidecar-совместимый manifest
- ✅ Sidecar extractor принимает published manifest wrapper
- ✅ Player читает local manifest без изменений runtime

---

### Phase 7 — PoP Ingest to Backend and Portal Reports

**Результат:** player пишет PoP → sidecar отправляет → backend принимает → portal показывает.

**Блокеры решаются:** B8.

**Что должно быть в commit:**
- Backend PoP ingest endpoint (уже частично есть, доработка)
- Portal reports page → реальные aggregated данные
- Базовая отчётность: показы по времени, статусы

**Тесты:**
- E2E: player PoP → sidecar send → backend ingest → portal query
- Проверка запрещённых полей в PoP payload
- Проверка корреляции PoP events

**Критерий готовности:**
- Portal reports показывает показы для пилотной кампании
- Данные агрегированы корректно
- Нет raw данных в UI

---

### Phase 8 — Pilot Rollout на группе КСО (следующий этап)

**Результат:** система работает на 3–5 реальных КСО в 2–3 магазинах.

**Блокеры решаются:** B9.

**Что должно быть в commit:**
- Фиксы по результатам test KSO проверки (Phase 8 = после успешного test KSO)
- Реальный Chromium kiosk launch
- Production device auth (mTLS)
- Media delivery (MinIO)
- Обновлённый runbook

**Тесты:**
- Дымовой тест на реальном оборудовании (3–5 КСО)
- 24–72ч стабильности
- Полная E2E цепочка с реальным UKM4

**Критерий готовности:**
- Креатив показывается на реальных КСО
- PoP поступает в backend
- Отчёт виден в портале
- Система стабильна ≥ 72 часа

---

## Acceptance Criteria

### Test KSO Technical Validation (текущий этап)

1. **Auth:** пользователь входит в портал, сессия работает
2. **Hierarchy:** виден 1 магазин и 1 КСО (synthetic seed)
3. **Content:** synthetic креатив 1440×1080 загружен через портал
4. **Campaign:** кампания создана, расписание назначено
5. **Approval:** кампания утверждена (1 шаг maker-checker)
6. **Publication:** manifest сгенерирован и опубликован
7. **Delivery:** sidecar fetch contract проверен (smoke)
8. **Display:** player smoke shell snapshot валиден
9. **PoP:** событие принято backend через TEST_ONLY endpoint
10. **Reports:** ✅ портал показывает PoP события через backend API

### Pilot Rollout (следующий этап)

1. Реальный Chromium kiosk показывает креатив
2. Реальный UKM4 state через state adapter
3. Production device auth (mTLS) на device gateway
4. Media доставляется через MinIO
5. 3–5 КСО в 2–3 магазинах
6. Стабильность ≥ 72 часа
7. Excel export (RLS-aware)

---

## Rollback Plan

1. **Stop KSO services:** `systemctl stop kso-player kso-sidecar kso-state-adapter`
2. **Restore default state:** `VERNY_KSO_STATIC_STATE=unknown`
3. **Clear runtime data:** `/var/lib/verny/kso/*`, `/run/verny/kso/*`
4. **Restore previous release package:** из backup
5. **Verify health:** backend `/health`, portal `/health`
6. **Rollback decision:** по результатам пилота

---

## Security Gates

| Gate | Проверка | Перед фазой |
|---|---|---|
| SG1 | Нет raw secrets/tokens в UI | Phase 4+ |
| SG2 | Нет backend URL в клиентском коде | Phase 4+ |
| SG3 | Auth enforced на всех portal endpoints | Phase 2+ |
| SG4 | RBAC enforced на backend API | Phase 2+ |
| SG5 | device_service machine-only не нарушен | Phase 3+ |
| SG6 | Manifest не содержит media bytes | Phase 6+ |
| SG7 | PoP payload не содержит raw IDs | Phase 7+ |
| SG8 | Excel export (если включён) учитывает RLS | Phase 7+ |

---

## Test Plan

### Regression Suites (каждая фаза)

| Suite | Команда | Ожидание |
|---|---|---|
| Portal web | `python3 -m unittest discover -s apps/portal-web/tests -v` | Все pass |
| State adapter | `python3 -m unittest discover -s apps/kso_state_adapter/tests -v` | Все pass |
| Player | `python3 -m unittest discover -s apps/kso_player/tests -v` | Все pass |
| Sidecar | `python3 -m unittest discover -s apps/kso_sidecar_agent/tests -v` | Все pass |
| Infra | `python3 -m unittest discover -s infra/kso-linux/tests -v` | Все pass |
| Backend | `python3 -m pytest backend/tests/ -v` | Все pass |
| Backend /health | `curl http://127.0.0.1:8001/health` | 200 |

### New Tests (per phase)

| Phase | Новые тесты |
|---|---|
| Phase 2 | Auth flow, JWT, session, RBAC middleware |
| Phase 3 | Organization CRUD, device registration |
| Phase 4 | Upload validation, media storage |
| Phase 5 | Campaign/schedule/approval workflow |
| Phase 6 | E2E manifest generation and delivery |
| Phase 7 | E2E PoP ingest and report aggregation |
| Phase 8 | Smoke test on real hardware |

---

## Файлы

- `docs/audit/one-kso-pilot-readiness-plan.md` — этот документ (test KSO → pilot rollout)
- `docs/audit/test-kso-end-to-end-readiness-gate.md` — **readiness gate с пошаговой E2E проверкой, stop criteria, rollback**
- `docs/audit/test-kso-deployment-dry-run.md` — **deployment dry run checklist (37.13)**
- `docs/audit/technical-debt-register.md` — **technical debt register (37.14, 36 пунктов)**
- `docs/audit/technical-debt-next-actions.md` — **next actions plan (37.14)**
- `docs/audit/full-system-audit-tz-v2-5.md` — полный аудит системы
- `infra/kso-linux/README.md` — KSO Linux deployment

## Обновления

### Шаг 37.1 — Hierarchy & KSO Device Registry Foundation (2026-06-22)

✅ **Foundation для one-KSO pilot готова:**

- **Branch**: `demo_branch_north` — читается/создаётся через `/api/branches`
- **Cluster**: `demo_cluster_001` — с полем `code`, unique(branch_id, code)
- **Store**: `demo_store_001` — с полями `format` (supermarket), `status` (active)
- **KsoDevice**: `demo_kso_001` — 1920×1080, ad zone 1440×1080, channel=kso

**Что закрыто:**
- 1 филиал + 1 кластер + 1 магазин + 1 КСО в backend
- KSO device registry с device_code, статусами, версиями, геометрией экрана
- Idempotent synthetic seed
- API: GET/POST/PUT `/api/devices/kso`
- Permissions: `devices.read`, `devices.manage`
- Миграция: 024 (clusters.code, stores.format/status, kso_devices)

**Следующий шаг:** Подключение portal-web к hierarchy API.

### Шаг 37.9 — Sidecar Fetch Published Manifest + Player Local Smoke (2026-06-22)

✅ **Цепочка доставки подтверждена без изменения production кода.**

### Шаг 37.10 — PoP Ingest Minimal for Test KSO Technical Validation (2026-06-22)


### Шаг 37.11 — Portal PoP Report Minimal for Test KSO Technical Validation (2026-06-16)

✅ **Portal PoP view готов — цепочка замкнута на уровне видимости в портале.**

- **Backend endpoint:** `GET /api/proof-of-play/test-kso` — safe projection list с фильтрами (device_code, campaign_code, creative_code, placement_code, date_from, date_to, limit)
- **Permission:** `reports.read` (уже в seed)
- **Safe projection:** event_code, device_code, placement_code, campaign_code, creative_code, media_ref, event_type, status, played_at, duration_ms, received_at
- **Portal page:** `/proof-of-play` — backend-driven (не DEMO), KPI-карточки (всего событий, уникальных КСО, уникальных кампаний), фильтр-форма (серверный GET, без JS), таблица safe-событий
- **Portal BackendClient:** `list_pop_events(access_token, filters)` — httpx GET с urlencode

**Что НЕ делалось:**
- Power BI, Excel экспорт, drill-down, сложные графики — не делались
- Billing/pricing, advertiser portal — не делались
- SSO/AD/MFA — не делались
- KSO player/sidecar/state-adapter runtime — не менялся
- Реальные UKM4/receipt/payment/fiscal данные — не читались
- Tokens/password_hash/backend URL/file_path/sha256/storage_ref/minio/raw IDs — не отображаются в HTML/logs/API

**Forbidden fields в ответе и шаблоне:** id (raw UUID), manifest_version_id, manifest_hash, backend_url, tokens, file_path, sha256, storage_ref, minio, device_secret, client_secret, receipt, payment, fiscal, customer, phone, email, card, pan.

**Техническая цепочка замкнута на уровне видимости в портале:**
creative → campaign → placement → approval → manifest → publish → sidecar/player smoke → PoP ingest → **portal PoP view** ✅

**Тесты:** backend 169/169, portal 407/407. Все regression suites green.
**Commit:** `📊 Add test KSO proof of play portal report (Step 37.11)`

✅ **Minimal TEST_ONLY PoP ingest готов:**

- **Домен:** `backend/app/domains/proof_of_play/` — модели, схемы, сервис, роутер
- **Модель:** `KsoProofOfPlayEvent` — bridge-таблица с safe-code корреляцией (device_code, placement_code, campaign_code, creative_code, manifest_code, media_ref)
- **Эндпоинт:** `POST /api/device-gateway/kso/{device_code}/pop` — **TEST_ONLY** без аутентификации
- **Корреляция:** `device_code → latest published GeneratedManifest → placement_code → KsoPlacement → campaign_code → creative_code`
- **Проверки:** manifest_version_id/hash (опциональные), media_ref в manifest items
- **Дубликаты:** idempotent accepted (тот же event_code → возвращается existing)
- **Миграция:** 030

**Что НЕ менялось:**
- Enterprise PoP (`proof_of_play_events`, `proof_of_play_batches`, `/api/device-gateway/pop/events*`) — не тронут
- KSO runtime (player, sidecar, state-adapter) — не менялся
- Portal — не менялся (отчёты будет шаг 37.11)
- Production auth — намеренно не реализован (TEST_ONLY)

**Forbidden fields:** receipt, payment, fiscal, customer, phone, email, card, pan, sha256, storage_ref, file_path, tokens, secrets — не принимаются и не сохраняются.

**Тесты:** backend 28 тестов (модели, схемы, хелперы, сервис с моками, sidecar-совместимость).

**Следующий шаг:** ✅ Выполнен (37.11).

### Шаг 37.12 — Test KSO End-to-End Readiness Gate (2026-06-16)

✅ **Readiness gate создан.**

- **Документ:** `docs/audit/test-kso-end-to-end-readiness-gate.md` — полный readiness gate с:
  - Что уже готово (16 компонентов, все ✅)
  - Параметры test KSO (железо, экран 1920×1080, ad zone 1440×1080, Chromium kiosk, UKM4)
  - Конфиги (sidecar.env, player.env, state-adapter.env — без секретов)
  - Локальные workspace paths на КСО
  - Имена сервисов systemd
  - **Пошаговая E2E проверка (11 шагов):** creative upload → campaign → placement → approval → manifest generation → publish → sidecar fetch → player smoke → PoP ingest → portal view
  - Критерии успеха (7 пунктов)
  - **Stop criteria (8 ситуаций с действиями)**
  - **Rollback процедура (6 шагов)**
  - Что НЕ готово для pilot rollout (8 пунктов)
  - Что нужно после успешной test KSO проверки (9 этапов)
- **Пилотный план переименован:** `one-kso-pilot-readiness-plan.md` → различие между test KSO (1 КСО) и pilot rollout (группа КСО) явно обозначено
- **Acceptance Criteria** разделены на test KSO (10 пунктов) и pilot rollout (7 пунктов)
- **Phase 8** переименован в Pilot Rollout (3–5 КСО, 72ч стабильности)
- Код НЕ менялся. Runtime НЕ менялся. Новый функционал НЕ добавлялся.

**Regression:** все suites green (backend 169, portal 407, state adapter 86, player 968, sidecar 1838, infra 227).
**Commit:** `📋 Add test KSO end-to-end readiness gate (Step 37.12)`

### Шаг 37.13 — Test KSO Deployment Dry Run (2026-06-16)

✅ **Deployment dry run проверен — блокеров нет.**

- **Документ:** `docs/audit/test-kso-deployment-dry-run.md`
- **Bootstrap installer:** ✅ 23/23 тестов, dry-run по умолчанию
- **Preflight validator:** ✅ 29/29 тестов, read-only
- **Systemd units × 3:** ✅ 73/73 тестов, env examples без секретов
- **Release package builder:** ✅ 28/28 тестов, dry-run по умолчанию
- **Пути:** `/opt/verny/kso`, `/etc/verny/kso`, `/var/lib/verny/kso`, `/run/verny/kso`, `/var/log/verny/kso` — совпадают с readiness gate
- **Геометрия:** 1920×1080 экран, 1440×1080 ad zone — совпадает
- **Команды dry-run:** bootstrap, preflight, release builder, UKM4 discovery — все без реальных изменений
- **Checklists:** dev-машина (8 пунктов), test KSO на месте (14 пунктов)
- Код НЕ менялся. Runtime НЕ менялся. Новый функционал НЕ добавлялся.

**Regression:** все suites green.
**Commit:** `📋 Add test KSO deployment dry run checklist (Step 37.13)`

### Шаг 37.14 — Technical Debt Register & Pilot Hardening Backlog (2026-06-16)

✅ **Реестр технического долга создан.**

- **Документы:**
  - `docs/audit/technical-debt-register.md` — полный реестр (36 debt items)
  - `docs/audit/technical-debt-next-actions.md` — краткий план действий
- **Выявлено debt items: 36** (P0=3, P1=9, P2=11, P3=13)
- **P0 блокирует physical test KSO:**
  - P0-1: TEST_ONLY unauthenticated manifest endpoint
  - P0-2: TEST_ONLY unauthenticated PoP endpoint
  - P0-3: In-memory portal session store
- **P1 блокирует pilot rollout:** 9 пунктов (MFA/SSO, RLS, synthetic context, creative lifecycle, media delivery, device credentials, test-kso wrappers, portal DEMO pages, observability)
- **Рекомендуемый порядок:** сейчас ничего не менять → после test KSO закрыть P0 → после успешной проверки закрыть P1 → после pilot закрыть P2/P3
- Код НЕ менялся. Runtime НЕ менялся. Новый функционал НЕ добавлялся.

**Regression:** все suites green.
**Commit:** `📋 Add technical debt register and pilot hardening backlog (Step 37.14)`

### Шаг 37.15 — Isolated Test KSO Risk Acceptance Update (2026-06-16)

✅ **Risk acceptance задокументирован.**

- **Physical test KSO в изолированном контуре:** P0-1, P0-2, P0-3 временно приняты как controlled risk
- **Условия допуска (7 пунктов):** изолированный контур, firewall, synthetic данные, нет реальных данных, ограниченное окно, документированный rollback, TEST_ONLY маркировка
- **Что НЕ разрешено:** pilot rollout, production, internet-facing, реальные данные
- **P0 закрывается перед pilot rollout** production-grade механизмами (device auth, mTLS, persistent session)
- **Документы обновлены (4):** technical-debt-register.md (секция 2a + поля Risk acceptance), next-actions.md, readiness-gate.md, deployment-dry-run.md
- Код НЕ менялся. Runtime НЕ менялся.

**Regression:** все suites green.
**Commit:** `📋 Document isolated test KSO risk acceptance (Step 37.15)`

### Шаг 38.0.8 — Local Kill-Switch File Flag (2026-06-24)

✅ **Kill-switch реализован — интеграция с shell plan.**

- **Модуль:** `kso_player/kill_switch.py` — `is_kill_switch_active(path)` чистая функция
- **Путь по умолчанию:** `/run/verny/kso/kill_switch`
- **Правила:** file exists → active, not exists → inactive, любая ошибка → active (fail-safe)
- **Интеграция:** `build_shell_plan(kill_switch_active=...)`, `validate_shell_plan_with_kill_switch()`
- **Поведение:** kill-switch active → force hidden даже при state=idle; geometry/safety флаги сохранены
- **Тесты:** 41 (file existence, error safety, bad paths, shell plan integration, immutability, no leaks)
- NO Chromium, NO X11, NO HTTP, NO backend, NO UKM5 DB
- КСО не менялась. Физический player не запускался. Legacy landscape тесты зелёные.

**Regression:** все suites green (backend 169, portal 407, state adapter 86, player 1139, sidecar 1838, infra 227 — **3866 всего**).
**Commit:** `🛑 Add local player kill switch`

### Шаг 38.0.9 — State Observer Stub / Safe Idle-Only (2026-06-24)

✅ **State observer реализован — интеграция с shell plan.**

- **Модуль:** `kso_player/state_observer.py` — `PlayerStateSnapshot` frozen dataclass + safe reader
- **API:** `from_dict()`, `read_state_snapshot()`, `resolve_visibility()`
- **Правила:** idle → visible; все остальные (busy/scan/cart/payment/error/offline/unknown/stale) → hidden
- **Fail-safe:** отсутствующий файл, битый JSON, permission error, forbidden fields → UNKNOWN/hidden
- **Forbidden fields:** receipt, transaction, payment, fiscal, customer, card, pan, phone, email, cashier, UKM5 DB, MySQL, Redis, secrets
- **Интеграция:** `apply_state_snapshot(plan, snapshot, kill_switch)` — единая точка разрешения видимости
- **Тесты:** 114 (snapshot construction/validation, staleness, from_dict с forbidden fields, reader все ошибки, visibility, shell plan интеграция, immutability, no leaks)
- NO Chromium, NO X11, NO HTTP, NO subprocess, NO UKM5 DB, NO MySQL
- КСО не менялась. Физический player не запускался. Legacy landscape тесты зелёные.

**Regression:** все suites green (backend 169, portal 407, state adapter 86, player 1253, sidecar 1838, infra 227 — **3980 всего**).
**Commit:** `🛡 Add safe player state observer stub`

### Шаг 38.0.10 — Local Smoke Harness (2026-06-24)

✅ **Local smoke harness реализован — pure orchestration без Chromium/Xvfb/сети.**

- **Модуль:** `kso_player/portrait_smoke.py` — `run_portrait_smoke()` + `SmokeResult` dataclass
- **Pipeline:** state.json → state_observer → kill_switch → shell_plan → visible/hidden
- **CLI:** `python -m kso_player.portrait_smoke --state-file ... --kill-switch ...` → prints safe JSON
- **SmokeResult:** только safe поля (profile_code, state, visible_plan, reason, geometry, flags)
- **No forbidden output:** receipt, payment, fiscal, customer, card, pan, phone, email, token, secret, password, backend_url, file_path, sha256, media_path, ukm5, mysql
- **Тесты:** 42 (idle→visible, все hidden состояния, missing/broken/forbidden/stale файлы, kill-switch override, geometry, safe JSON, no network/X11/subprocess imports)
- NO Chromium, NO X11, NO Xvfb, NO network, NO subprocess, NO UKM5 DB
- КСО не менялась. Физический player не запускался.

**Regression:** все suites green (backend 169, portal 407, state adapter 86, player 1295, sidecar 1838, infra 227 — **4022 всего**).
**Commit:** `🧪 Add portrait overlay local smoke harness`

### Шаг 38.0.11 — Physical KSO Manual Test Plan (2026-06-24)

✅ **План ручной проверки создан — код и КСО не менялись.**

- **Документ:** `docs/audit/portrait-overlay-physical-kso-test-plan.md`
- **Phase 0:** Readiness check (5 мин, 5 шагов)
- **Phase 1:** Dry smoke без UI (10 мин, 6 шагов: idle/ks/unknown/stale/payment/busy-error-offline) — **одобрено**
- **Phase 2:** Overlay render — **НЕ одобрен**, требует отдельного manual approval
- **Phase 3:** Rollback (5 мин, 7 шагов)
- **Stop criteria:** 9 ситуаций (перекрытие оплаты, зависание УКМ5, потеря фокуса Chromium, CPU/RAM, ошибка кассы, потеря SSH/VNC, чековые данные)
- **Approval gate:** явное разделение dry smoke (✅) vs overlay render (⛔ requires approval)
- Код не менялся. КСО не менялась.

### Шаг 38.1 — Physical KSO Phase 0–1 Execution (2026-06-24)

✅ **Phase 0 пройден.** SSH доступ, УКМ5 active, RAM 1.9 GB, Chromium 114 kiosk 768×1024.
✅ **Phase 1 пройден 6/6** на Python 3.6.9 через standalone smoke-скрипт.
⛔ **Phase 2 НЕ одобрен.** Overlay render не запускался. УКМ5 не менялась.

- **Standalone smoke:** `apps/kso_player/scripts/standalone_smoke_py36.py` (Python 3.6+, self-contained)
- **Микросекунды:** `.573421Z` → `idle_visible` ✅ (`strptime` + `%f`)
- **Временные файлы на КСО очищены**
- **Тесты:** +3 (timestamp с микросекундами, stale, missing state) в `test_state_observer.py`
- **Phase 2 требует отдельного explicit manual approval Сергея Пащенко**
- Код не менялся (standalone скрипт — новый файл, не модуль kso_player).
