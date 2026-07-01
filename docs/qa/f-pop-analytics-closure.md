# F — PoP & Analytics Closure Gate

**Status:** CLOSED  
**Date:** 2026-07-10  
**Commit:** (see report)

---

## Executive Summary

Phase F реализовала read-only analytics/reporting layer: нормализацию PoP-событий из двух источников (KSO + Enterprise Gateway), агрегацию метрик, API и portal-страницу. ClickHouse не включался. Миграции не добавлялись. PoP ingestion / Device Gateway / KSO / publication не менялись.

---

## Phase F Scope

| Step | Что сделано | Commit |
|---|---|---|
| F.0 | Design Gate — анализ PoP-контуров, 12 метрик | `4d8b164` |
| F.1 | Analytics Schemas/Contracts — 13 Pydantic-моделей | `50a3c23` |
| F.2 | PoP Mapping & Normalization Service | `801d49c` |
| F.3 | Delivery Aggregation Service | `2b0988a` |
| F.3.1 | Delivery Aggregation Coverage & Docs Gate | `d6bbff1` |
| F.4 | Analytics API Read-Only — 4 endpoints | `206fdb0` |
| F.4.1 | Analytics API Security / RLS / Regression Gate | `1eb0f51` |
| F.5 | Portal Reports Read-Only | `998f5d4` |

---

## PoP Source of Truth

| Source | Model | Production? | Dry-run excluded? |
|---|---|---|---|
| Legacy KSO | `KsoProofOfPlayEvent` | ✅ да | ✅ `is_dry_run=False` |
| Enterprise Gateway | `ProofOfPlayEvent` | ✅ да | ✅ `details_json.dry_run` check |
| Universal Manifest preview | — | ❌ нет | ✅ исключён |

---

## Normalization Summary

`normalize_pop_events(db, query)` → `list[PopEventNormalized]`

- **14 полей** в `PopEventNormalized`
- **2 normalizers:** `_normalize_legacy_kso_pop_event()`, `_normalize_enterprise_gateway_pop_event()`
- **Correlation status:** matched / partial / unmatched
- **Scope filtering:** 6 измерений (campaign, placement, store, device, gateway, channel)
- **channel_code warning** (channel_id not resolved)

---

## Aggregation Summary

`calculate_delivery_metrics(db, query)` → `DeliveryMetricResult`

- **14 метрик** (delivered_impressions, proof_events_count, playback_success/failure, manifest_received, device/active/silent counts)
- **Playback statuses:** 5 success + 5 failure
- **Manifest received:** 3 event types
- **6 breakdowns:** campaign, placement, store, device, channel, day
- **Placement/store:** структурно поддержаны, пока "unknown" (JOIN deferred)
- **Expected impressions:** None (planning integration deferred)
- **Device health:** базовый (active/silent по last_seen)

---

## Analytics API Summary

| Метод | Path | Returns |
|---|---|---|
| `GET` | `/api/analytics/delivery/summary` | `DeliveryMetricResult` |
| `POST` | `/api/analytics/delivery/query` | `DeliveryMetricResult` |
| `GET` | `/api/analytics/planned-vs-delivered` | `PlannedVsDeliveredResult` |
| `GET` | `/api/analytics/device-health` | `DeviceHealthResult` |

- Permission: `reports.read`
- RLS: `_enforce_scope()` — 5 scope измерений, broad-deny → 403
- Audit: 4 `analytics.*.viewed` события
- No-secrets: `validate_no_secrets_in_analytics_payload()` перед ответом

---

## Portal Reports Summary

- Page: `/reports/analytics` — «Аналитика показов»
- Permission: `reports.read`
- Blocks: Сводка доставки, План/факт, Здоровье устройств, Детализация (6 таблиц)
- Filters: date_from, date_to, channel_code
- Error states: no data, no plan, 403, backend error, «Не определено»
- Security: server-side rendering, без CDN/JS/localStorage/secrets

---

## Security / RLS / Audit Summary

| Check | Результат |
|---|---|
| `reports.read` — единственная permission | ✅ |
| `analytics.read` не создавался | ✅ |
| Scoped user broad query → 403 | ✅ |
| Cross-advertiser → 404 (без утечки ID) | ✅ |
| Cross-store → 404 | ✅ |
| channel_code не bypass'ит scope | ✅ |
| 4 audit события | ✅ |
| Denied requests без success audit | ✅ |
| Audit без secrets | ✅ |
| Device service без доступа | ✅ |

---

## No-Secrets Summary

- ✅ Ответы API без password/token/secret/api_key
- ✅ Portal HTML без secrets/CDN/JS/traceback
- ✅ `validate_no_secrets_in_analytics_payload()` в каждом handler
- ✅ Audit details без forbidden fields

---

## Read-Only / Data Safety Summary

- ✅ KsoProofOfPlayEvent — только SELECT
- ✅ ProofOfPlayEvent — только SELECT
- ✅ GeneratedManifest не пишется
- ✅ PoP ingestion не менялся
- ✅ Device Gateway не менялся
- ✅ KSO Adapter не менялся
- ✅ Universal Manifest не менялся
- ✅ Publication flow не менялся
- ✅ Portal без CRUD
- ✅ ClickHouse не импортируется
- ✅ Миграции не создавались
- ✅ DROP/DELETE/TRUNCATE нет

---

## Test Results

| Слой | Тестов | Результат |
|---|---|---|
| F.1 targeted | 42 | 42/42 ✅ |
| F.2 targeted | 54 | 54/54 ✅ |
| F.3 targeted | 69 | 69/69 ✅ |
| F.4 targeted | 60 | 60/60 ✅ |
| F.4.1 targeted | 43 | 43/43 ✅ |
| F.5 targeted | 44 | 44/44 ✅ |
| **Analytics suite** | **268** | **268/268 ✅** |
| **Backend collection** | **2145** | **0 errors ✅** |
| **Portal full regression** | **974 collected** | **934 passed / 32 skipped / 8 pre-existing** |

### Portal baseline explanation

- **Старый baseline (after E/D):** 930 collected / 890 passed / 32 skipped / 8 errors
- **Новый baseline (after F.5):** 974 collected / 934 passed / 32 skipped / 8 errors
- **Δ: +44 collected, +44 passed** — ровно F.5 targeted tests
- **8 pre-existing errors:** `test_portal_backend_live_integration.py::TestPermissionMapConsistency` — требуют запущенный backend, не связаны с Phase F
- F.5 regression report (858/20) был **subset** (5 test files), не full suite

---

## ClickHouse Decision

**ClickHouse НЕ включён.** Pipeline не создавался, импорты отсутствуют, миграции не добавлялись.

Реализованная архитектура (F.2 normalize → F.3 aggregate → F.4 API → F.5 portal) работает напрямую на PostgreSQL через SQLAlchemy SELECT. Этого достаточно для текущих объёмов.

ClickHouse может быть рассмотрен в отдельном performance gate (F.6+), но не раньше.

---

## Deferred Items

1. ClickHouse pipeline
2. Placement/store JOIN resolution в normalizers
3. expected_impressions из planning (planned vs delivered полноценный)
4. Silent device detection (expected device set)
5. Export reports (PDF/XLSX/CSV)
6. Portal advanced filters
7. Performance indexes / materialized daily aggregates
8. Production KSO switch (отдельный design gate)

---

## What Next Phase Must Not Break

- Analytics API contract (4 endpoints)
- Analytics service (normalize → aggregate pipeline)
- Portal page `/reports/analytics`
- RLS/scope enforcement
- No-secrets validation
- Read-only boundaries (no PoP/Gateway/KSO/publication writes)

---

## GO / NO-GO

**✅ GO для Phase G — design gate / pre-audit**

**NO-GO** для прямого включения ClickHouse без performance gate.  
**NO-GO** для production KSO switch без отдельного design gate.
