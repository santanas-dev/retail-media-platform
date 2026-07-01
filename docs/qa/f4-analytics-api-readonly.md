# F.4 — Analytics API Read-Only

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

F.4 добавляет 4 read-only API endpoints поверх analytics service (F.2/F.3). Все используют существующую permission `reports.read`. RLS через `resolve_user_scope_context`. Audit через `audit_business_action`.

---

## Endpoints

| Метод | Path | Описание | Permission |
|---|---|---|---|
| `GET` | `/api/analytics/delivery/summary` | Delivery metrics summary (query params) | `reports.read` |
| `POST` | `/api/analytics/delivery/query` | Delivery metrics full query (JSON body) | `reports.read` |
| `GET` | `/api/analytics/planned-vs-delivered` | Planned vs delivered comparison | `reports.read` |
| `GET` | `/api/analytics/device-health` | Device health report | `reports.read` |

### Query params (GET summary / planned-vs-delivered)

`date_from`, `date_to`, `granularity`, `advertiser_id`, `campaign_id`, `placement_id`, `store_id`, `device_id`, `gateway_device_id`, `physical_device_id`, `channel_id`, `channel_code`, `include_legacy_kso`, `include_enterprise_gateway`, `exclude_dry_run`

### POST body (delivery/query)

`DeliveryMetricQuery`: `time_range`, `scope`, `include_legacy_kso`, `include_enterprise_gateway`, `exclude_dry_run`

### Device health params

`date_from`, `date_to`, `store_id`, `channel_code`, `gateway_device_id`, `physical_device_id`, `silent_threshold_minutes`

---

## Permission

Используется **`reports.read`** — существующая permission, уже используемая:
- `/api/reports/pop` (PoP list)
- `/api/reports/campaigns/export`
- `/api/airtime/report`
- `/api/reports/publications/export`

Все 4 endpoints требуют `reports.read`. Без неё — 401/403.

**Новая permission `analytics.read` не создавалась** — чтобы избежать seed/RLS gate в F.4. При необходимости можно добавить в F.5+.

---

## RLS / Scope

RLS через `resolve_user_scope_context(db, current_user)` → `UserScopeContext`.

### Admin (system_admin, security_admin)
- Полный доступ — broad query без фильтров разрешён.

### Scoped users (advertiser / store)
- **Broad query без scope-фильтра → 403 Forbidden** с сообщением: «укажите хотя бы один фильтр»
- **С конкретным объектом** (`campaign_id`, `placement_id`, `advertiser_id`) → проверка через `assert_object_in_advertiser_scope()` (404 при нарушении scope)
- **С `store_id`** → проверка через `assert_object_in_store_scope()`

### Защита от утечки
- Cross-advertiser query → 404 (не 403, чтобы не раскрывать существование объекта)
- Error messages не содержат внутренних ID/traceback

---

## Audit

4 audit events (fire-and-forget через `audit_business_action`):

| Event | Endpoint | Target |
|---|---|---|
| `analytics.delivery.summary.viewed` | GET /delivery/summary | campaign/placement/advertiser/store_id |
| `analytics.delivery.query.viewed` | POST /delivery/query | campaign/placement/advertiser/store_id |
| `analytics.planned_vs_delivered.viewed` | GET /planned-vs-delivered | campaign/placement/advertiser/store_id |
| `analytics.device_health.viewed` | GET /device-health | store_id |

Audit details: `result_summary`, `campaign_id`/`placement_id`/`advertiser_id`/`store_id` (если заданы). Без паролей, токенов, secrets — `FORBIDDEN_DETAILS` stripping.

---

## Response safety

- `validate_no_secrets_in_analytics_payload(result.model_dump())` перед ответом
- При обнаружении secrets → `result.ok = False`, `result.errors` пополняется
- No raw `details_json`
- No credentials/secrets/tokens
- No stack traces
- Errors/warnings structured (`AnalyticsIssue`)

---

## Invalid input handling

| Ситуация | Код | Ответ |
|---|---|---|
| Невалидный UUID | 422 | `"Invalid UUID format: ..."` |
| Невалидный datetime | 400 | `"Invalid datetime format: ..."` |
| date_from > date_to | 400 | `"date_from must be <= date_to"` |
| Невалидная granularity | 400 | `"granularity must be one of [total, day, hour]"` |
| Нет permission | 401/403 | Standard FastAPI auth error |
| Нет данных | 200 | `DeliveryMetricResult` с нулевыми метриками |

---

## Read-only boundaries

F.4 **НЕ делает**:
- ❌ Миграции
- ❌ ClickHouse
- ❌ Portal changes
- ❌ PoP event create/update
- ❌ GeneratedManifest write
- ❌ Device Gateway endpoint changes
- ❌ KSO Adapter changes
- ❌ Publication flow
- ❌ Domain-data DB writes (audit writes разрешены — стандартный механизм проекта)

---

## Тесты

| Слой | Тестов |
|---|---|
| F.4 targeted | **60** |
| F.3 targeted | 69 |
| F.2 targeted | 54 |
| F.1 targeted | 42 |
| **Analytics suite** | **225** |
| Backend collection | **2102 / 0 errors** |

### F.4 test groups

| Группа | Тестов | Темы |
|---|---|---|
| Route registration | 5 | router exists, 4 endpoints |
| Permissions | 5 | 401/403 без reports.read |
| Delivery summary | 10 | params, validation, responses |
| Delivery query | 6 | POST body, no-secrets, UUID validation |
| Planned vs delivered | 4 | response shape, expected=None |
| Device health | 4 | response, threshold, no fake devices |
| RLS/Scope | 6 | admin broad, scoped narrow, no leakage |
| Audit | 6 | all 4 handlers, no secrets in audit |
| Read-only boundaries | 8 | no DB writes, no ClickHouse, no portal |
| Compatibility | 6 | F.1/F.2/F.3 files, existing endpoints |

---

## GO / NO-GO

**✅ GO для F.5 — Portal Reports**

Причины:
1. 4 endpoints, все защищены `reports.read`
2. RLS/scope: scoped users ограничены, admin — полный доступ
3. Audit: 4 события, no-secrets safe
4. Invalid input: structured 400/422 errors
5. Read-only: нет миграций, ClickHouse, portal, DB writes
6. Analytics suite: 225/225
7. Backend collection: 2102 / 0 errors
8. Существующие `/reports/pop` endpoints нетронуты
9. Документация создана

**Deferred до F.5+:**
- `analytics.read` как отдельная permission (если потребуется более тонкий доступ)
- Scope enforcement на уровне ответа (авто-фильтрация вместо 403 для broad queries)
- Channel-specific RLS
