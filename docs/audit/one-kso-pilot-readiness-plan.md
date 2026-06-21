# One-KSO Pilot Readiness Plan

> **Статус:** 📋 Audit / Roadmap
>
> Дата: 2026-06-21
> Шаг: 36.1
> Ревизия: 1

## Target Pilot Scenario

**Цель:** установить плеер на 1 КСО, загрузить через портал креатив, назначить расписание, опубликовать manifest, показать креатив на КСО, получить Proof-of-Play и увидеть отчётность в портале.

**Целевое оборудование:** ServPlus Sherman-J 5.1 (Linux), СуперМаг УКМ 4, Chromium kiosk.

**Минимальный объём:** 1 магазин, 1 КСО, 1 креатив, 1 кампания, 1 расписание, 1 публикация, 1 PoP-событие.

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
| 16 | Сформировать manifest | PARTIAL | backend/publications | KSO manifest projection (backend) | Portal→backend trigger → manifest generation | ❌ |
| 17 | Опубликовать manifest | DEMO_ONLY | portal-web + backend | Publications page DEMO, publications domain | Portal→backend publish API | ❌ |
| 18 | Sidecar забирает manifest/media | DONE | kso_sidecar_agent | Manifest sync, media sync, gateway client | Реальный backend URL | ❌ |
| 19 | Player показывает креатив | DONE (tests) | kso_player | Display cycle, playlist, render plan | Реальный Chromium + manifest + media | ❌ |
| 20 | Player создаёт PoP | DONE (tests) | kso_player | PoP writer, JSONL events | Реальный playback | ❌ |
| 21 | Sidecar отправляет PoP | DONE (tests) | kso_sidecar_agent | PoP pickup, batch, send, rotation | Реальный backend URL | ❌ |
| 22 | Backend принимает PoP | PARTIAL | backend/device_gateway | PoP ingest domain, batch ingest | Real E2E: sidecar→backend | ❌ |
| 23 | Portal показывает отчёт | DEMO_ONLY | portal-web + backend | Reports page placeholder, campaign_reports domain | Portal→backend API + real aggregation | ✅ P0 |
| 24 | Excel export готовит выгрузку | MISSING | portal-web + backend | Export block disabled, RLS note | Real Excel generation + RLS filters | ❌ |

### Сводка по цепочке

| Статус | Шагов |
|---|---|
| ✅ DONE (в тестах) | 7 (6, 7, 8, 9, 18, 19, 20, 21) |
| 🟡 PARTIAL | 2 (16, 22) |
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
| CP7 | PoP ingest → portal reports | ❌ MISSING | Backend + Portal |
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

### Phase 6 — Manifest E2E Generation

**Результат:** portal → backend → manifest → sidecar pull → player display.

**Блокеры решаются:** B7.

**Что должно быть в commit:**
- Backend manifest endpoint (уже частично есть, доработка)
- Sidecar успешно забирает manifest через реальный backend
- Player отображает media из manifest

**Тесты:**
- E2E: публикация → manifest → sidecar sync → player playlist
- Проверка manifest формата (соответствие KSO-safe контракту)

**Критерий готовности:**
- Sidecar получает manifest от backend
- Player корректно читает manifest и media

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

### Phase 8 — One-KSO Pilot Deployment

**Результат:** система работает на 1 реальном КСО.

**Блокеры решаются:** B9.

**Что должно быть в commit:**
- Фиксы по результатам реального запуска
- Обновлённый runbook

**Тесты:**
- Дымовой тест на реальном оборудовании
- 24-шаговая цепочка пройдена

**Критерий готовности:**
- Креатив показывается на реальном КСО
- PoP поступает в backend
- Отчёт виден в портале
- Система стабильна ≥ 24 часа

---

## Acceptance Criteria for 1 KSO Pilot

1. **Auth:** пользователь входит в портал, сессия работает
2. **Hierarchy:** виден 1 магазин и 1 КСО
3. **Content:** креатив загружен через портал и проше вал валидацию
4. **Campaign:** кампания создана, расписание назначено
5. **Approval:** кампания утверждена (хотя бы 1 шаг)
6. **Publication:** manifest сгенерирован и опубликован
7. **Delivery:** sidecar получил manifest и media
8. **Display:** креатив отображается на КСО
9. **PoP:** события поступают в backend
10. **Reports:** портал показывает фактические показы

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

- `docs/audit/one-kso-pilot-readiness-plan.md` — этот документ
- `docs/audit/full-system-audit-tz-v2-5.md` — полный аудит системы
- `infra/kso-linux/README.md` — KSO Linux deployment
- `docs/kso/linux-kso-pilot-first-start-runbook.md` — pilot runbook
