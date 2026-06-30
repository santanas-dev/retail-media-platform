# TZ v2.5 Re-Alignment Roadmap — 46.1

> **Дата:** 2026-06-29
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
- Backend baseline: 947 collected, 881 passed, 66 pre-existing, 0 collection errors
- Portal baseline: 863 passed, 0 failed
- Все legacy таблицы сохранены, CRUD в portal не добавлен

### B.4 — Channel Orchestrator ✅ COMPLETED
- B.4.0 Design Gate — commit `a8a36b6`
- B.4.1 AdapterContract + MockAdapter + Registry — commit `7cae398`
- B.4.2 Orchestrator Service + Placement Target Resolution — commit `4503515`
- B.4.3 Simulation Engine — commit `4d6f71f`
- B.4.4 Closure Gate — commit `42b8f89`
- Components: `orchestrator/contracts.py`, `orchestrator/service.py`, `orchestrator/simulation.py`, `adapters/mock_adapter.py`, `adapters/registry.py`
- Tests: 79/79 (B.4.1 32 + B.4.2 25 + B.4.3 22)
- Backend baseline: 1129 collected, 1063 passed, 66 pre-existing, 0 collection errors

### B.5 — Universal Manifest Schema v1
- Core fields + adapter_payload
- Подпись (HMAC v1)
- Версионирование (manifest_schema_version)
- Валидация совместимости с capability profile

**Blockers:** нет (все mock)
**Risk:** High (архитектурный фундамент)
**KSO hardware:** не требуется

---

## Фаза C: Device Gateway (P1 — обязательно до пилота)

### C.1 — Device Registration
- `POST /device/register` — device_code + hardware_fingerprint
- Выдача device credentials (mock mTLS/JWT)
- Привязка к physical_device + store

### C.2 — Device Auth & Heartbeat
- Device authentication flow
- `POST /device/heartbeat` — статус, версия плеера, capability profile
- Tracking: online/offline/degraded/error/maintenance

### C.3 — Manifest Pull (ETag/304)
- `GET /device/manifest` — pull manifest
- ETag/304 для неизменного manifest
- Совместимость: min_player_version check

### C.4 — PoP Ingestion (batch)
- `POST /device/pop/batch` — пакетная отправка
- Idempotency key
- Валидация подписи устройства
- Запись в ClickHouse

### C.5 — ClickHouse Setup
- Таблицы: pop_events, device_heartbeats, device_errors
- TTL/partitioning по датам
- Агрегаты для быстрых отчётов

**Blockers:** нет (mock device + ClickHouse docker)
**Risk:** High
**KSO hardware:** не требуется

---

## Фаза D: Inventory & Planning (P1)

### D.1 — Inventory Rules Engine
- Правила ёмкости по каналам
- Расчёт: свободно/занято/зарезервировано/продано
- Прогноз показов по поверхностям

### D.2 — Conflict Engine
- Пересечение расписаний
- Превышение допустимой рекламной нагрузки
- Приоритеты и вытеснение

### D.3 — Simulated Publication
- «Что если» перед публикацией
- Sold out + альтернативы
- Overbooking policy (default: запрещён)

**Blockers:** нужен Channel Orchestrator (B.4)
**KSO hardware:** не требуется

---

## Фаза E: KSO — Первый канал (P1)

### E.1 — KSO Adapter
- Реализация KsoAdapter на основе AdapterContract
- mTLS/token flow (mock)  
- ETag/304, cache instructions
- Hidden-on-touch events

### E.2 — KSO Chromium Runtime (только при доступности КСО)
- systemd wrapper
- Chromium kiosk 1440×1080
- Локальный кэш, fallback

**Blockers:** 🔴 KSO hardware для E.2
**Risk:** Medium (адаптер без hardware можно через mock)

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

| Приоритет | Фазы | Блокирует | Можно без КСО |
|---|---|---|---|
| **P0** | A (Re-Alignment), B (Multichannel Core) | Всё остальное | ✅ Да |
| **P1** | C (Device Gateway), D (Inventory), E (KSO adapter) | Пилот | ✅ Да (кроме E.2) |
| **P2** | F (Analytics), G (Emergency/Ops) | Production | ✅ Да |
| **P3** | H (Production Readiness) | Запуск | ⚠️ Желательно |

## Оценка усилий

| Фаза | Сессий | Сложность |
|---|---|---|
| A — Re-Alignment | 2-3 | Medium |
| B — Multichannel Core | 4-6 | High |
| C — Device Gateway | 3-5 | High |
| D — Inventory | 2-3 | Medium |
| E — KSO Channel | 2-4 | Medium-High |
| F — PoP & Analytics | 3-5 | Medium-High |
| G — Emergency & Ops | 2-4 | Medium |
| H — Production | 3-5 | High |

**Итого: ~21-35 сессий до production-ready v2.5**
