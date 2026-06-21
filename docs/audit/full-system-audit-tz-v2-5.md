# Full System Audit — TZ v2.5 Alignment

> **Статус:** 📋 Audit / Design / Roadmap
>
> Дата: 2026-06-21
> Шаг: 36.1
> Ревизия: 1

## Executive Summary

Retail Media Platform прошла 35 шагов разработки (backend + KSO player + sidecar + state adapter + infra + portal-web). Система имеет работающий backend на FastAPI с 22 миграциями, полностью покрытый тестами KSO runtime (player 968, sidecar 1838, state adapter 86, infra 227), и web-портал с 289 тестами. Однако **ни один компонент не развёрнут на реальном оборудовании**. Портал работает на синтетических demo-данных. Auth, RBAC, RLS — только контракты. Нет реальной интеграции между порталом и backend.

**Общая оценка готовности к ТЗ v2.5: ~45%** (backend data model — 70%, KSO runtime — 85%, portal UI — 30%, integration — 5%, auth/RBAC/RLS enforcement — 0%).

**Готовность к пилоту на 1 КСО: ~15%** — требуется реализация критического пути (auth → hierarchy → creative upload → campaign → manifest → PoP → reports).

---

## Current System Map

```
┌─────────────────────────────────────────────────────────────┐
│                    WEB PORTAL (port 8002)                    │
│  FastAPI + Jinja2, 15 routes, synthetic DEMO data           │
│  Auth: contract only, login/logout disabled                 │
│  RBAC/RLS: contract only, 8 roles, matrix defined           │
│  Pages: dashboard, stores, devices, creatives, campaigns,   │
│          schedule, publications, approvals, reports,        │
│          deployment, PoP, admin, login, logout              │
│  Tests: 289 ✅                                              │
└───────────────────────────┬─────────────────────────────────┘
                            │ NO REAL INTEGRATION
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (port 8001)                        │
│  FastAPI, 22 migrations, 22 domains                         │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────┐   │
│  │channels      │ │identity      │ │organization       │   │
│  │(9 types)     │ │(users/roles) │ │(hierarchy)        │   │
│  ├──────────────┤ ├──────────────┤ ├───────────────────┤   │
│  │advertisers   │ │media         │ │campaigns          │   │
│  │(brands, etc) │ │(upload, S3)  │ │(lifecycle)        │   │
│  ├──────────────┤ ├──────────────┤ ├───────────────────┤   │
│  │scheduling    │ │publications  │ │inventory          │   │
│  │(slots)       │ │(manifest)    │ │(capacity)         │   │
│  ├──────────────┤ ├──────────────┤ ├───────────────────┤   │
│  │device_gateway│ │device_ops    │ │campaign_reports   │   │
│  │(auth,pull)   │ │(alerts,cfg)  │ │(aggregation)      │   │
│  └──────────────┘ └──────────────┘ └───────────────────┘   │
│  Tests: backend tests exist, not run in this audit         │
│  /health → 200 ✅                                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  KSO PLAYER     │ │  SIDECAR     │ │  STATE ADAPTER   │
│  (Chromium)     │ │  (sync/PoP)  │ │  (UKM4/safe)     │
│  968 tests ✅   │ │  1838 tests✅ │ │  86 tests ✅     │
│  CLI: daemon,   │ │  CLI: daemon,│ │  CLI: daemon,    │
│  loop, cycle,   │ │  sync, PoP   │ │  write-once      │
│  snapshot       │ │  rotation    │ │                  │
└─────────────────┘ └──────────────┘ └──────────────────┘
              │             │              │
              └─────────────┼──────────────┘
                            │
              ┌─────────────┴──────────────┐
              │     INFRA (kso-linux)      │
              │  systemd × 3, bootstrap,   │
              │  preflight, release pkg    │
              │  227 tests ✅              │
              └────────────────────────────┘
                            │
              ┌─────────────┴──────────────┐
              │     KSO SIMULATOR          │
              │  local FS, manifest reader │
              │  smoke tests               │
              └────────────────────────────┘
```

---

## TZ v2.5 Compliance Matrix

| # | Раздел ТЗ | Статус | Детали |
|---|---|---|---|
| 1 | **Архитектура Control Plane** | PARTIAL | Backend data model есть. API endpoints частично реализованы. Web portal disconnected. |
| 2 | **Device Gateway** | PARTIAL | Модели и auth есть. Pull-модель реализована в sidecar. Gateway endpoint работает. |
| 3 | **Content Service** | PARTIAL | Media domain есть (upload, storage). Но нет реальной интеграции с порталом. |
| 4 | **Inventory** | PARTIAL | Domain есть (capacity, stores). Не подключён к порталу. |
| 5 | **Manifest** | PARTIAL | Publication domain + manifest projection. KSO-safe manifest в sidecar. |
| 6 | **Proof of Play** | PARTIAL | PoP ingest domain есть. Sidecar pickup/send реализован. Но backend → portal chain не замкнута. |
| 7 | **Analytics / BI** | CONTRACT_ONLY | Campaign reports domain есть (модели). Portal BI — placeholder HTML/CSS charts без JS. Excel export disabled. |
| 8 | **Emergency** | CONTRACT_ONLY | Alert models есть. Emergency stop описан в RLS_RULES. Не реализован. |
| 9 | **Audit** | CONTRACT_ONLY | Audit logging описан в security contract. Не реализован в backend. Portal admin audit — placeholder. |
| 10 | **Технологический стек** | DONE | FastAPI, PostgreSQL, ClickHouse (planned), MinIO (planned), Redis (planned), Chromium kiosk — зафиксированы. |
| 11 | **Auth / users / RBAC / RLS / MFA** | CONTRACT_ONLY | 8 ролей, 19 permissions, 7 RLS scopes. Contract + tests. Нет backend enforcement. Нет session management. |
| 12 | **Локальная авторизация портала** | CONTRACT_ONLY | Local auth supported, user management defined. Login/logout pages — placeholders, кнопки disabled. |
| 13 | **Admin users/roles/RLS** | CONTRACT_ONLY | Admin page renders per-role views + RLS matrix. Все controls disabled. |
| 14 | **Иерархия сеть→филиал→кластер→магазин→КСО** | PARTIAL | Organization domain есть (модели). Seed data есть. Portal stores/devices — DEMO only. |
| 15 | **КСО Linux/Chromium player** | DONE | 968 тестов. Daemon, loop, cycle, snapshot. Shell bootstrap. Safety enforced. |
| 16 | **State Adapter / UKM4 safe state** | DONE | 86 тестов. Static + file source. SafeStatusFileSource. Systemd unit. |
| 17 | **Sidecar / manifest sync / media sync** | DONE | 1838 тестов. Pull model. Media cache. Runtime config sync. Heartbeat. |
| 18 | **Manifest generation and validation** | PARTIAL | Backend: KSO manifest projection implemented. Sidecar: safe manifest extractor. Не tested E2E portal→backend→sidecar. |
| 19 | **Media upload / creative validation** | PARTIAL | Media domain (models, storage, S3). Portal creatives page — DEMO only. Upload не реализован. |
| 20 | **Campaign workflow** | DEMO_ONLY | Backend campaign domain есть. Portal — DEMO data + lifecycle в UI. CRUD не реализован. |
| 21 | **Schedule / inventory** | DEMO_ONLY | Backend scheduling domain есть. Portal schedule — DEMO only. |
| 22 | **Approvals / maker-checker** | CONTRACT_ONLY | Backend orchestrator domain есть (пустой). Maker-checker описан в RLS_RULES + docs. Portal approvals — DEMO only. |
| 23 | **Publication workflow** | DEMO_ONLY | Backend publications domain есть. Portal publications — DEMO only. |
| 24 | **Reports / BI / Excel export** | DEMO_ONLY | Backend campaign_reports domain есть. Portal reports — placeholder HTML charts, Excel disabled. |
| 25 | **Deployment / install / rollback** | DONE | Bootstrap, preflight, release package builder, systemd × 3, pilot runbook, rollback plan. 227 тестов. |
| 26 | **Monitoring / health / audit** | PARTIAL | Health endpoint. Alerts domain. Heartbeat. Sidecar status. No dashboard monitoring. |
| 27 | **Security requirements** | PARTIAL | Forbidden fields enforced. No raw secrets in UI. Safe output in player. device_service=machine-only contract. No backend RBAC/RLS enforcement. |
| 28 | **One-KSO pilot readiness** | BLOCKER | См. отдельный анализ — 24-шаговая цепочка не замкнута. |

### Сводка

| Статус | Количество |
|---|---|
| DONE | 5 (стек, player, state adapter, sidecar, deployment) |
| PARTIAL | 10 |
| CONTRACT_ONLY | 6 |
| DEMO_ONLY | 5 |
| MISSING | 0 |
| BLOCKER | 1 (pilot readiness) |
| RISK | 0 |

---

## Module-by-Module Audit

### Backend (`backend/`)

| Параметр | Значение |
|---|---|
| Фреймворк | FastAPI |
| Миграции | 22 (Alembic) |
| Доменов | 13 |
| Таблиц | ~30+ |
| Запущен | ✅ port 8001, /health → 200 |
| Тесты | Есть (backend/tests/ — 10 файлов) |

**Что работает:**
- Инициализация БД и миграции
- Seed (channels, identity)
- KSO manifest projection (backend → sidecar формат)
- KSO media delivery (media reference resolver)
- PoP ingest / batch ingest (модели)
- Device gateway auth (pull-модель, JWT secret)
- Device operations (alerts, runtime config)
- Campaign reports (модели, агрегация)
- Organization hierarchy (модели)

**Что не работает / не подключено:**
- Auth (нет session/JWT для portal users)
- RBAC enforcement (permissions не проверяются на API)
- RLS enforcement (scopes не применяются к запросам)
- Direct portal→backend API integration отсутствует
- Real media upload pipeline
- Real campaign/schedule/approval workflow
- Real Excel export
- Real BI aggregation

### KSO Player (`apps/kso_player/`)

| Параметр | Значение |
|---|---|
| Тесты | 968 ✅ |
| Модулей | 18 Python |
| Player shell | 5 файлов (HTML, JS, CSS) |

**Статус: DONE.** Полностью покрыт тестами. CLI: daemon, loop, cycle, snapshot. Safety enforced. No network, no secrets, no media bytes in output. Read-only consumer. Совместим с manifest форматом sidecar.

### KSO Sidecar Agent (`apps/kso_sidecar_agent/`)

| Параметр | Значение |
|---|---|
| Тесты | 1838 ✅ |
| Модулей | 37 Python |
| Pyproject | Есть |

**Статус: DONE.** Pull model. Auth, heartbeat, manifest sync, media sync, runtime config sync. PoP pickup, rotation, send. Все HTTP-клиенты тестируются с fake http.server.

### KSO State Adapter (`apps/kso_state_adapter/`)

| Параметр | Значение |
|---|---|
| Тесты | 86 ✅ |
| Модулей | 6 Python |

**Статус: DONE.** Static + file source. SafeStatusFileSource (1024B лимит, forbidden keys, allowed roots). Fail-closed. Player Wants (не Requires).

### Web Portal (`apps/portal-web/`)

| Параметр | Значение |
|---|---|
| Тесты | 289 ✅ |
| Страниц | 15 routes |
| Шаблонов | 15 HTML |

**Статус: DEMO_ONLY.** Все данные синтетические (DEMO: prefix). Все controls disabled. Auth — только placeholder (кнопки disabled). RBAC/RLS — только contract (security_contract.py). Нет интеграции с backend API.

### Infra (`infra/kso-linux/`)

| Параметр | Значение |
|---|---|
| Тесты | 227 ✅ |
| Systemd units | 3 |
| Bootstrap | kso_linux_bootstrap.py |
| Preflight | kso_linux_preflight.py |
| Release | package builder + manifest |

**Статус: DONE.** Контракт каталогов, env examples, systemd hardening. Bootstrap safe-by-default (dry-run). Preflight validator (readonly). Pilot runbook.

---

## Security Audit

| Проверка | Статус |
|---|---|
| Raw secrets в UI | ✅ Нет (FORBIDDEN_FIELDS_ALL) |
| Token/password в коде | ✅ Нет (только в .env) |
| Внешние CDN/scripts/fonts | ✅ Нет |
| Real personal data | ✅ Нет (все DEMO:) |
| Чеки/платёжные/фискальные данные | ✅ Нет |
| Прямой доступ КСО к admin endpoints | ✅ Player/sidecar не вызывают admin API |
| device_service machine-only | ✅ Контракт уточнён (шаг 35.2.2.1) |
| RLS enforcement | ❌ Только contract |
| Excel export RLS | ❌ Не реализован |
| BI drill-down RLS | ❌ Не реализован |
| Approval final required | ❌ Contract only |
| Maker-checker | ❌ Contract only |

---

## Architecture Deviations from TZ

### Осознанные и допустимые

| Отклонение | Обоснование |
|---|---|
| KSO-first, не multichannel-ready core | Каналы (Android/LED/ESL) зафиксированы в channels domain, но UI v1 — KSO-only. Channel-agnostic core задекларирован, но не реализован. |
| Portal disconnected from backend | Осознанная стратегия: сначала UI foundation, потом API integration. |
| Auth/RBAC/RLS — contract only | Осознанно: безопасность требует backend enforcement, который ещё не реализован. |
| Demo data вместо real API | UI разрабатывается независимо от backend API. |

### Опасные

| Отклонение | Риск | Рекомендация |
|---|---|---|
| Нет API-first контракта между portal и backend | Portal pages могут не соответствовать backend API schema | Создать OpenAPI контракт до начала интеграции |
| Campaign/schedule/publication workflow — только UI placeholder | Бизнес-логика не проверена | Реализовать backend workflow до пилота |
| Нет real auth session | Без auth нельзя проверить RBAC/RLS | Приоритет Phase 2 |

---

## Risks

| # | Риск | Вероятность | Влияние | Статус |
|---|---|---|---|---|
| 1 | Portal API schema не совпадёт с backend schema | Средняя | Высокое | RISK |
| 2 | KSO player не запустится на реальном оборудовании ServPlus Sherman-J 5.1 | Средняя | Критичное | RISK |
| 3 | UKM 4 state adapter не получит реальные данные | Средняя | Критичное | RISK |
| 4 | Chromium kiosk mode нестабилен на целевом железе | Средняя | Высокое | RISK |
| 5 | Manifest generation содержит ошибки для реальных данных | Средняя | Высокое | RISK |
| 6 | Media upload pipeline не обрабатывает реальные форматы КСО | Средняя | Высокое | RISK |
| 7 | PoP correlation не работает для реальных показов | Низкая | Среднее | RISK |
| 8 | Systemd services не стартуют на целевом Linux | Низкая | Критичное | RISK |
| 9 | Portal performance с real data | Низкая | Среднее | RISK |
| 10 | SSO/AD интеграция сложнее ожидаемого | Средняя | Среднее | RISK |

---

## Blockers (для пилота на 1 КСО)

| # | Блокер | Приоритет |
|---|---|---|
| B1 | Нет real auth (session/JWT) | P0 |
| B2 | Нет real user CRUD | P0 |
| B3 | Portal не подключён к backend API | P0 |
| B4 | Нет real media upload pipeline | P0 |
| B5 | Нет campaign → schedule → publication workflow | P0 |
| B6 | Нет E2E manifest generation (portal → backend → sidecar) | P0 |
| B7 | Нет E2E PoP (player → sidecar → backend → portal reports) | P0 |
| B8 | КСО не развёрнуто на реальном оборудовании | P0 |

---

## Recommendations

1. **API-first**: создать OpenAPI контракт portal↔backend до интеграции
2. **Auth first**: session/JWT + local user CRUD + RBAC enforcement
3. **Hierarchy first**: завести 1 реальный филиал → магазин → КСО
4. **Creative upload**: минимальный pipeline для 1440×1080 PNG/JPEG
5. **Campaign MVP**: создать → согласовать → опубликовать на 1 КСО
6. **E2E manifest**: portal → backend manifesto → sidecar pull → player display
7. **E2E PoP**: player write → sidecar pickup → backend ingest → portal report
8. **Pilot deploy**: установить на 1 реальное КСО

---

## Decision Log Needed

| # | Решение | Кто принимает |
|---|---|---|
| D1 | План первоочередных шагов | Архитектор |
| D2 | API contract portal↔backend | Архитектор |
| D3 | Подход к auth (локальный + SSO или только локальный для пилота) | Архитектор |
| D4 | Минимальный набор полей для creative upload | Архитектор + бизнес |
| D5 | Формат manifest для первого пилота | Архитектор |
| D6 | Подход к real PoP correlation | Архитектор |

---

## Файлы контракта

- `docs/audit/full-system-audit-tz-v2-5.md` — этот документ
- `docs/audit/one-kso-pilot-readiness-plan.md` — план готовности к пилоту
- `apps/portal-web/security_contract.py` — auth/RBAC/RLS контракт
- `docs/portal/rls-role-portal-views.md` — RLS матрица
- `docs/portal/auth-rbac-rls-foundation.md` — auth foundation
- `docs/architecture.md` — общая архитектура
- `infra/kso-linux/README.md` — KSO Linux infra
- `docs/kso/linux-kso-pilot-first-start-runbook.md` — pilot runbook
