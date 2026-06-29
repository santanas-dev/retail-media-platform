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

### A.3 — KSO Data Migration Dry-Run ✅ DONE
- Dry-run SQL (`docs/architecture/kso-data-migration-dry-run-a3.sql`)
- Migration plan: 4 tables, 4 rows total, field-level mapping
- Backup plan, validation plan, rollback plan
- Feature flag: USE_UNIVERSAL_DEVICE_MODEL
- **Миграция НЕ выполнена** — готово к исполнению после approval

**Blockers:** нет
**Risk:** Medium (data migration)
**KSO hardware:** не требуется

---

## Фаза B: Multichannel Core (P0 — блокеры архитектуры)

### B.1 — Channel Registry Cleanup
- Убрать KSO-дубликаты из кода
- Дополнить seed: Android TV, price checker, ESL, LED как каналы
- Валидация: все 5 каналов в `channels` таблице

### B.2 — Device Model Unification  
- `physical_devices` как единая модель для всех каналов
- `logical_carriers` и `display_surfaces` для ESL/LED сценариев
- `capability_profiles` для каждого device_type
- Убрать `kso_devices` после миграции

### B.3 — Placement как отдельная сущность
- Выделить Placement из Campaign (где/когда/как/какой канал)
- Campaign 1→N Placements
- Placement связан с display_surfaces через Channel Orchestrator

### B.4 — Channel Orchestrator (скелет)
- `orchestrator/service.py` — сборка manifest
- `orchestrator/simulation.py` — симуляция перед публикацией
- `orchestrator/contracts.py` — AdapterContract интерфейс
- Mock adapter для тестов

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
