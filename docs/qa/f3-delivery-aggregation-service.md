# F.3 — Delivery Aggregation Service

**Status:** COMPLETED (F.3.1 coverage gate)  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

`calculate_delivery_metrics(db, query)` реализует read-only агрегацию поверх `normalize_pop_events()` (F.2). Никаких API, миграций, ClickHouse, portal и записи в БД.

### Pipeline

```
query (DeliveryMetricQuery)
  → валидация time_range, granularity, sources
  → normalize_pop_events(db, query)    — F.2: чтение KsoProofOfPlayEvent + ProofOfPlayEvent
  → exclude_dry_run_events()           — если query.exclude_dry_run=True
  → _aggregate_metrics(events)          — DeliveryMetricsSummary
  → _build_breakdowns(events, granularity) — 6 измерений
  → DeliveryMetricResult
```

---

## Реализованные метрики

| Метрика | Формула | Источник |
|---|---|---|
| `delivered_impressions` | `sum(e.delivered_impressions)` | `PopEventNormalized.delivered_impressions` |
| `proof_events_count` | `len(events)` | — |
| `playback_success_count` | `count(e.playback_status ∈ SUCCESS)` | см. статусы ниже |
| `playback_failure_count` | `count(e.playback_status ∈ FAILURE)` | см. статусы ниже |
| `manifest_received_count` | `count(e.event_type ∈ MANIFEST_TYPES)` | см. event types ниже |
| `device_count` | `unique(device_code, gateway_device_id, physical_device_id)` | — |
| `active_device_count` | то же, что device_count для событий в периоде | — |
| `silent_device_count` | `0` (требует expected device set — F.4+) | warning: `silent_device_requires_inventory_or_device_scope` |
| `expected_impressions` | `None` (требует planning integration — F.4+) | warning: `expected_impressions_unavailable` |
| `delivery_gap_percent` | `None` (без expected) | — |
| `*_delivery_status` | `"unknown"` | — |

### Playback statuses

**Success** (`PLAYBACK_SUCCESS_STATUSES`):
`success`, `played`, `completed`, `ok`, `accepted`

**Failure** (`PLAYBACK_FAILURE_STATUSES`):
`failure`, `failed`, `error`, `rejected`, `timeout`

### Manifest received event types

`MANIFEST_RECEIVED_EVENT_TYPES`:
`manifest_received`, `manifest_downloaded`, `received`

---

## Breakdowns

Поддержаны **6 измерений**:

| Breakdown | Ключ | Источник поля | Статус |
|---|---|---|---|
| `campaign` | `campaign_id` или `"unknown"` | `PopEventNormalized.campaign_id` | ✅ полноценный |
| `placement` | `placement_id` или `"unknown"` | `PopEventNormalized.placement_id` | ⚠️ unknown (см. ниже) |
| `store` | `store_id` или `"unknown"` | `PopEventNormalized.store_id` | ⚠️ unknown (см. ниже) |
| `device` | `device_code` / `gateway_device_id` / `"unknown"` | `PopEventNormalized` | ✅ |
| `channel` | `channel_code` или `"unknown"` | `PopEventNormalized.channel_code` | ✅ |
| `day` | `YYYY-MM-DD` / `"unknown"` (только при granularity=day/hour) | `event_time.date()` | ✅ |

### Placement и store: documented limitation

`placement_id` и `store_id` **присутствуют в схеме** `PopEventNormalized`, и breakdowns по ним **реализованы и отдают корректную структуру**. Однако оба нормализатора (`_normalize_legacy_kso_pop_event`, `_normalize_enterprise_gateway_pop_event`) выставляют эти поля в `None`, потому что:

- **placement_id** требует JOIN к `manifest_version → publication_target → placement` (enterprise) или `placement_code → Placement` (KSO)
- **store_id** требует JOIN к `GatewayDevice.store_id` (enterprise) или отсутствует в KSO-модели

Все события попадают в бакет `"unknown"`. В `calculate_delivery_metrics()` добавляется warning:
```
metric_limited: placement_id and store_id not resolved by normalizers
— all events fall into 'unknown' bucket for these dimensions (deferred to F.4+)
```

Реальные данные по placement/store появятся после доработки нормализаторов (F.4+), но **структура API стабильна** — она уже включает placement и store breakdowns.

### Unknown bucket

Если ключевое поле отсутствует (None) — используется `key="unknown"`. Это не теряет события: сумма метрик по "unknown" + реальным бакетам всегда равна total.

Консистентность подтверждена тестами для **всех 6 измерений** (placement, store, campaign, channel, device, day).

---

## Dry-run exclusion

Через `exclude_dry_run_events()`: фильтрует `PopEventNormalized.is_dry_run == True`. Legacy KSO события всегда `is_dry_run=False`. Enterprise события проверяют `details_json.dry_run`.

`query.exclude_dry_run=True` по умолчанию.

---

## Planned vs Delivered

`calculate_planned_vs_delivered(db, query)`:
- `delivered_impressions` — из факта (через `calculate_delivery_metrics()`)
- `expected_impressions` — `None` (нет planning integration в F.3)
- `status` — `"no_plan"` (при `include_planning=True`) или `"no_plan"` (без planning)
- warning: `expected_impressions_unavailable`

---

## No-secrets

`validate_no_secrets_in_analytics_payload()` проверяет результат на 23 запрещённых ключа/значения:
`password`, `token`, `secret`, `api_key`, `bearer`, `cookie`, `session`, `jwt`, `signature`, `credential`, etc.

Все метрики и breakdowns валидируются — ни один forbidden key не попадает в результат.

---

## Read-only boundaries

F.3 **НЕ делает**:
- ❌ API/router
- ❌ Миграции
- ❌ ClickHouse
- ❌ Portal changes
- ❌ DB writes (`db.add/insert/commit`)
- ❌ Device Gateway endpoint changes
- ❌ KSO Adapter changes
- ❌ Publication flow
- ❌ GeneratedManifest writes

---

## Тесты

### F.3 targeted: 69/69 (F.3.1 coverage)

| Группа | Тестов | Темы |
|---|---|---|
| Metric basics | 5 | zero, sums, counts |
| Playback statuses | 5 | success, failure, unknown |
| Manifest received | 3 | event_type counting |
| Device counts | 4 | unique, active, silent |
| Expected / gap | 7 | unavailable, formula, statuses |
| Breakdowns | 16 | 6 измерений, unknown, consistency sums |
| Query / source | 5 | date range, scope, dry-run |
| Planned vs delivered | 5 | result shape, status, defaults |
| No-secrets | 5 | summary, breakdown, result, placement/store |
| Boundaries | 10 | no db, no api, no clickhouse, no portal, docs exist |
| Regression | 4 | F.1/F.2 files, status sets, forbidden keys |

### Analytics suite: 165/165 (F.1: 42 + F.2: 54 + F.3: 69)

### Backend collection: см. отчёт

---

## GO / NO-GO

**✅ GO для F.4 — Analytics API Read-Only**

Причины:
1. Все 6 измерений структурно поддержаны (placement/store — "unknown" бакет, стабильная структура API)
2. Консистентность сумм подтверждена для всех измерений
3. 69 targeted tests, все pass
4. No-secrets валидация на месте
5. Read-only boundaries подтверждены: нет API, миграций, ClickHouse, portal, DB writes
6. Документация создана (`docs/qa/f3-delivery-aggregation-service.md`)
7. Analytics suite: 165/165

**Deferred до F.4+:**
- placement_id/store_id разрешение в нормализаторах (JOIN'ы к manifest_version, GatewayDevice)
- expected_impressions из planning
- silent_device_count из inventory
