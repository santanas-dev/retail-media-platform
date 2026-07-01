# TZ v2.5 Re-Alignment Roadmap — 46.1

> **Дата:** 2026-06-29 (обновлено 2026-07-01 после Phase E)
> **Предыдущий roadmap:** `roadmap-after-full-audit-45-7.md` — ЗАМЕНЯЕТСЯ этим документом
> **Причина:** Gap analysis показал значительные отклонения от ТЗ v2.5

## Stop/Go

**❌ ОСТАНОВЛЕНО:**
- 46.1 Compliance (уже сделано достаточно)
- 46.2 Pilot Readiness (преждевременно — нет Device Gateway)
- Все UX/статусные hardening (достаточно для v1)
- Разработка KSO-специфичных модулей

**✅ ПРОДОЛЖИТЬ:** Полная перестройка по архитектуре ТЗ v2.5

---

## Фаза A: Re-Alignment (немедленно)

### A.1 — TZ v2.5 Gap Analysis ✅ DONE
- Документ: `docs/audit/tz-v2-5-gap-analysis-46-1.md`
- Документ: `docs/architecture/v2-5-architecture-correction-plan-46-1.md`

### A.2 — ERD/API/Event Contracts v2.5 ✅ DONE
- Зафиксировать ERD v2.5 (PostgreSQL) на основе ТЗ Table 17+34
- Зафиксировать API contracts по группам (ТЗ Table 19)
- Зафиксировать event stream contracts (ТЗ Table 33)
- Документы в `docs/architecture/`

### A.3 — KSO Data Migration ✅ EXECUTED (commit cb7f294)
- Schema: ALTER physical_devices + 3 CREATE TABLE
- Data: 4 INSERTs (1 device + 1 placement + 1 target + 2 PoP)
- FK fix: proof_events.manifest_id → generated_manifests
- Validation: 17/17 checks pass
- Legacy kso_* tables preserved

### A.3.1 — Migration Approval Gate ✅ APPROVED & EXECUTED
- Mini-design, approval checklist, risk matrix
- `APPROVE A.3 EXECUTION` получено, миграция выполнена

### A.3.2 — Post-Migration Safety Gate ✅ VERIFIED
- Backup: 2.2 MB, 634 entries, проверен
- Data quality: 17/17
- Regression: Backend 848/0, Portal 842/32sk
- Feature flag: NOT implemented (safe)
- No DROP/DELETE/TRUNCATE
- ✅ READY FOR B.1

---

## Фаза B: Multichannel Core (P0 — блокеры архитектуры)

### B.1 — Channel Registry Cleanup ✅ COMPLETED
- Seed: 5 device types (+4), 6 capability profiles, orientation fix
- Universal read helpers: channel_code filter, by-external-code lookup
- ORM: external_code + device_properties on PhysicalDevice
- Tests: 15/15
- Compatibility layer documented
- Legacy routes/tables preserved
- **KSO = первый канал, не отдельная вертикаль**

### B.2 — Device Model Unification ✅ COMPLETED
- Full chain: PD→LC→DS→CP for all devices
- KSO device: +logical_carrier +display_surface (portrait 768×1024)
- Placement target: linked to display_surface
- Service helpers: get_device_surfaces, get_device_capabilities, get_surface_readiness
- API: GET /api/physical-devices/{id}/surfaces, GET /api/display-surfaces/{id}/readiness
- Tests: 19/19 (chain integrity, KSO device, placement link, no orphans)

### B.3 — Placement как отдельная сущность ✅ COMPLETED
- B.3.0 Design Gate: Placement model v1, channel_id FK, Campaign 1→N Placement
- B.3.1 Schema Migration: Alembic 034, placements.channel_id NOT NULL, ORM models
- B.3.2 Service + API: 12 service functions, 7 endpoints, RBAC/RLS, audit (4 actions)
- B.3.3 Functional Validation: 31 tests, seed idempotency, DB integrity checks
- B.3.3.1 Regression Delta: +9 pre-existing failures classified, 16 real API/RLS tests
- B.3.4 Portal Read-Only: campaign detail placements block + /placements/{id} detail page

### B.4 — Channel Orchestrator ✅ COMPLETED
- B.4.0 Design Gate — commit `a8a36b6`
- B.4.1 AdapterContract + MockAdapter + Registry — commit `7cae398`
- B.4.2 Orchestrator Service + Placement Target Resolution — commit `4503515`
- B.4.3 Simulation Engine — commit `4d6f71f`
- B.4.4 Closure Gate — commit `a6db738`
- Components: `orchestrator/contracts.py`, `orchestrator/service.py`, `orchestrator/simulation.py`, `adapters/mock_adapter.py`, `adapters/registry.py`
- Tests: 79/79 (B.4.1 32 + B.4.2 25 + B.4.3 22)

### B.5 — Universal Manifest Schema v1 ✅ COMPLETED
- B.5.0 Design Gate — commit `83c8dc9`
- B.5.1 Schema Contracts (10 Pydantic models, 3 validators) — commit `4d6c2d4`
- B.5.2 Manifest Builder from Orchestrator Draft — commit `9bd663f`
- B.5.3 Enhanced Validation + No-Secrets — commit `f3b767e`
- B.5.4 Legacy Compatibility Analysis — commit `f079e8b`
- B.5.5 Closure Gate — commit `b043a43`
- Components: `universal_schema.py` (666 строк), `universal_builder.py` (382 строки)
- Tests: 115/115 (37+38+40)
- Universal Manifest — preview/draft/internal path only
- Production path — legacy GeneratedManifest (unchanged)

---

## Фаза C: Device Gateway (P1 — обязательно до пилота) — ✅ COMPLETED

> **Уточнение:** Device Gateway уже существовал на ~80% до Phase C (JWT auth, admin API, device endpoints, heartbeat, PoP, config/media/manifest delivery). Phase C провёл аудит, добавил universal manifest delivery, и закрыл security/regression покрытие.

### C.0 — Pre-C Design Gate ✅ (commit `0d6ba19`)
- Аудит: Gateway 80% готов (gateway_devices, JWT auth, admin API, device API)
- Gap: Universal manifest delivery через Device Gateway
- GO для C.1

### C.1 — Universal Manifest Device Gateway Delivery ✅ (commit `01932b1`)
- Новый endpoint: `GET /api/device-gateway/manifest/universal/current`
- Resolver: GatewayDevice → Placement → UniversalManifestV1
- ETag/304, no_manifest structured responses
- 12 targeted tests

### C.1.1 — Security & Regression Gate ✅ (commit `8e01d89`)
- Coverage gap закрыт: 12 → 39 тестов (+27)
- Auth, secrets, legacy endpoint preservation
- Import boundary verification

### C.2 — Device Registration Validation ✅ (commit `2281bb7`)
- Аудит: device_code validation, credential lifecycle, device states
- 39 тестов: schema, bcrypt, timing-safe, JWT claims, permissions

### C.3 — Heartbeat / Device Status Validation ✅ (commit `68d0db2`)
- Аудит: record_heartbeat(), status transitions, forbidden keys
- 44 теста: auth, validation, side-effects, response safety

### C.4 — Manifest Pull Dry-Run / Delivery Validation ✅ (commit `3ee274b`)
- Аудит: все 3 manifest endpoints (legacy, KSO, universal)
- 60 тестов: auth, delivery, ETag, no_manifest, read-only, safety

### C.5 — Closure Gate ✅
- Документы: `c-device-gateway-closure.md`, `current-project-state-after-c.md`
- Backend: 1426 collected / 1360 passed / 66 pre-existing / 0 errors
- Gateway Suite: 195/195

---

## Фаза D: Inventory & Planning (P1) — ✅ COMPLETED

> **Реализовано:** D.0–D.6 (11 commits). Planning schemas, service functions (availability, conflicts, occupancy, scenario), read-only Planning API (5 endpoints), portal planning visibility.
> **Read-only foundation:** booking/reservation workflow deferred.
> **Closure doc:** `docs/qa/d-inventory-planning-closure.md`
> **Project state:** `docs/product/current-project-state-after-d.md`

### D.1 — Inventory Rules Engine ✅
- Правила ёмкости по каналам — check_availability()
- Расчёт: свободно/занято/зарезервировано/продано — calculate_occupancy()
- Фильтры по 5 измерениям, non-sellable exclusion

### D.2 — Conflict Engine ✅
- Пересечение расписаний — check_conflicts()
- Превышение допустимой рекламной нагрузки
- Приоритеты и вытеснение (conflict_type, severity)

### D.3 — Simulated Publication ✅
- «Что если» перед публикацией — simulate_planning_scenario() (скелет)
- Planning API: 5 read-only endpoints
- Portal: planning block на campaign detail

---

## Фаза E: KSO — Первый канал (P1) ✅ COMPLETED

### E.0 — Pre-E Audit / Design Gate ✅
- Анализ legacy KSO flow, universal chain, gaps
- Документ: `docs/architecture/e0-kso-first-channel-design-gate.md`

### E.1 — KSO Adapter Contract + Dry-Run Payload Builder ✅
- KsoAdapter(AdapterContract) — dry-run payload builder
- auto-register через _register()
- build_payload/validate_payload/simulate_delivery
- 55 tests

### E.2 — Validation + No-Secrets / Compatibility Gate ✅
- FORBIDDEN_SECRET_WORDS: 20 слов, ALLOWED_SAFE_KEYS
- Рекурсивный no-secrets scanner
- Payload compatibility validation
- 65 tests

### E.3 — Universal Manifest Preview Integration ✅
- KsoAdapter → select_adapter("kso") → UniversalManifestV1.adapter_payload
- Gateway universal endpoint возвращает KSO preview manifest
- 52 tests

### E.4 — Legacy Compatibility / No Production Switch Gate ✅
- Legacy /kso/{device_code}/manifest изолирован
- GeneratedManifest не пишется universal preview path
- 0 production switch флагов
- 45 tests

### E.5 — Closure Gate ✅
- Финальный аудит, документация, baseline

**E total: 217 tests / 217 passed**

### Deferred (НЕ входило в scope E):
- KSO Chromium Runtime (заблокирован hardware)
- Real KSO production switch
- Compatibility projection
- Signed manifests
- GeneratedManifest writes из universal manifest
- Media delivery/caching для KSO

---

## Фаза F: PoP & Analytics (P1-P2)

### F.1 — Нормализованная Proof-модель
- Единая таблица `proof_events` с `proof_type`
- Типы: real_playback, idle_impression, template_applied, label_ack, controller_ack, delivery_ack
- Разделение: плановые показы vs фактические playback vs подтверждения доставки

### F.2 — Campaign Dashboard
- План/факт по кампании
- География, динамика по дням/часам
- Недопоказы и причины

### F.3 — Advertiser Portal (read-only)
- Свои кампании, понятные отчёты
- Экспорт PDF/XLSX/CSV
- Без технического шума

**Blockers:** нужен PoP Ingestion (C.4) и ClickHouse (C.5)
**KSO hardware:** не требуется для mock-данных

---

## Фаза G: Emergency & Operations (P2)

### G.1 — Emergency Management
- Стоп-реклама, экстренное сообщение, возврат
- Уровни: устройство/магазин/кластер/филиал/сеть
- Аудит и прогресс доставки

### G.2 — Operational Health Center
- Дашборд здоровья устройств
- Детализация до магазина/устройства
- Алерты по критичным событиям

### G.3 — Staged Rollout
- Лаборатория → 5 магазинов → ... → вся сеть
- Авто-стоп при превышении порога ошибок
- Rollback на стабильную версию

**Blockers:** нужен Device Gateway + PoP
**KSO hardware:** желательно

---

## Фаза H: Production Readiness (P2-P3)

### H.1 — HA & Backups
- PostgreSQL standby, backup/restore drill
- ClickHouse репликация
- MinIO отказоустойчивость

### H.2 — Load Testing
- Профиль: 40 000 устройств, heartbeat 30s, manifest pull 30s, PoP batch 60s
- Профиль: массовая публикация на всю сеть
- Профиль: аналитика по крупной кампании

### H.3 — Мониторинг
- Prometheus/Grafana метрики
- Алерты: массовый офлайн, рост ошибок PoP, недоступность Gateway
- Correlation ID / trace ID

**Blockers:** нужна работающая платформа (фазы B-F)
**KSO hardware:** желательно для реалистичных тестов

---

## Сводка приоритетов

| Приоритет | Фазы | Статус | Блокирует | Можно без КСО |
|---|---|---|---|---|
| **P0** | A (Re-Alignment), B (Multichannel Core) | ✅ COMPLETED | — | ✅ Да |
| **P1** | D (Inventory & Planning), E (KSO) | ✅ COMPLETED | — | ✅ Да |
| **P2** | F (Analytics), G (Emergency/Ops) | ⏳ | Production | ✅ Да |
| **P3** | H (Production Readiness) | ⏳ | Запуск | ⚠️ Желательно |

## Оценка усилий

| Фаза | Сессий | Сложность | Статус |
|---|---|---|---|
| A — Re-Alignment | 2-3 | Medium | ✅ |
| B — Multichannel Core | 4-6 | High | ✅ |
| C — Device Gateway | 3-5 | High | ✅ |
| D — Inventory & Planning | 11 | Medium | ✅ |
| E — KSO Channel | 5 | Medium | ✅ |
| F — PoP & Analytics | 3-5 | Medium-High | ⏳ |
| G — Emergency & Ops | 2-4 | Medium | ⏳ |
| H — Production | 3-5 | High | ⏳ |

**Итого: ~21-35 сессий до production-ready v2.5** | **Закрыто: A+B+C+D+E = ~24-30 сессий**
