# F.4.1 — Analytics API Security / RLS / Regression Gate

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

F.4.1 — security gate перед F.5 Portal Reports. Проверены: permission enforcement, RLS/scope, audit safety, no-secrets, read-only boundaries, source boundaries, compatibility.

---

## 1. Permission checks

| Проверка | Результат |
|---|---|
| Без auth → 401/403 | ✅ 5 тестов |
| Без `reports.read` → 403 (все 4 endpoints) | ✅ |
| `reports.read` требуется (не `planning.read`) | ✅ код-инспекция |
| `analytics.read` не создавался | ✅ |
| `device_service` bypass отсутствует | ✅ нет `authenticate_device` |

**Вывод:** `reports.read` — единственная permission для всех 4 endpoints. `planning.read`, `device_service` не дают доступ. Новая permission не создавалась.

---

## 2. RLS / Scope checks

| Проверка | Механизм | Результат |
|---|---|---|
| Admin bypass (`ctx.is_admin`) | `_enforce_scope` возвращает ctx без проверок | ✅ |
| Broad query без scope-фильтра → 403 | `_enforce_scope`: `has_scope_filter=False` → 403 | ✅ |
| `campaign_id` scope check | `assert_object_in_advertiser_scope(adv_id, ctx)` | ✅ |
| `placement_id` scope check | через `Placement → Campaign → advertiser_id` | ✅ |
| `advertiser_id` scope check | `assert_object_in_advertiser_scope(advertiser_id, ctx)` | ✅ |
| `store_id` scope check | `assert_object_in_store_scope(store_id, ctx)` | ✅ |
| Cross-advertiser → 404 (не 403) | `assert_object_in_advertiser_scope` → `HTTP_404_NOT_FOUND` | ✅ |
| Cross-store → 404 (не 403) | `assert_object_in_store_scope` → `HTTP_404_NOT_FOUND` | ✅ |
| `channel_code` не bypass'ит scope | `has_scope_filter` не учитывает channel_code | ✅ |

**Вывод:** RLS реализован на уровне `_enforce_scope` с 5 scope-измерениями (campaign, placement, advertiser, store, broad-deny). Cross-advertiser → 404 без утечки существования.

---

## 3. Audit checks

| Проверка | Результат |
|---|---|
| Все 4 handler'а вызывают `_audit_analytics` | ✅ |
| Audit после no-secrets валидации, перед return | ✅ |
| `_audit_analytics` не содержит secret-полей | ✅ |
| `target_ref` — безопасный ID или "global" | ✅ |
| `_enforce_scope` вызывается ДО audit (denied → no audit) | ✅ |

**Вывод:** Audit пишется только для успешных запросов. Denied requests не генерируют audit. Audit details безопасны.

---

## 4. No-secrets checks

| Проверка | Endpoints | Результат |
|---|---|---|
| Ответы без password/token/secret/api_key/bearer/cookie/session/jwt/authorization | Все 4 | ✅ |
| `details_json` не возвращается | Все 4 | ✅ (нет в response model) |
| Stack traces не leak'ятся | 400 error path | ✅ |
| `validate_no_secrets_in_analytics_payload` вызывается | Все 4 handler'а | ✅ код-инспекция |

**Вывод:** Ни один endpoint не возвращает secrets/credentials/tracebacks.

---

## 5. Read-only boundaries

| Проверка | Файл | Результат |
|---|---|---|
| Нет `KsoProofOfPlayEvent` write | router.py | ✅ |
| Нет `ProofOfPlayEvent` write | router.py | ✅ |
| Нет `GeneratedManifest` write | router.py | ✅ |
| Нет `db.add/insert/update/delete` | service.py | ✅ |
| Нет publication import | service.py | ✅ |
| Нет GeneratedManifest import | router.py | ✅ |

**Вывод:** Analytics API не пишет в domain data. Audit write — штатный механизм.

---

## 6. Source boundaries

| Проверка | Результат |
|---|---|
| Нет ClickHouse import | ✅ |
| Нет Device Gateway router import | ✅ |
| Нет KSO Adapter import | ✅ |
| Нет portal/template/Jinja import | ✅ |

**Вывод:** Analytics router/service полностью изолированы — не зависят от ClickHouse, Gateway, KSO, portal.

---

## 7. Compatibility

| Проверка | Результат |
|---|---|
| `/reports/pop` нетронут | ✅ файл proof_of_play/router.py содержит `/reports/pop` |
| `/reports/pop/summary` нетронут | ✅ |
| F.1/F.2/F.3 тесты на месте | ✅ |
| F.4.1 не добавил новых endpoints | ✅ 4 decorators = 4 endpoints |

---

## Тесты

| Слой | Тестов |
|---|---|
| F.4.1 targeted | **43** |
| F.4 targeted | 60 |
| F.3 targeted | 69 |
| F.2 targeted | 54 |
| F.1 targeted | 42 |
| **Analytics suite** | **268** |
| Backend collection | **2145 / 0 errors** |

---

## GO / NO-GO

**✅ GO для F.5 — Portal Reports**

Все 7 категорий проверок пройдены:
1. ✅ Permission: `reports.read`, без утечек через planning.read/device_service
2. ✅ RLS/Scope: 5 измерений, cross-advertiser → 404, broad-deny → 403
3. ✅ Audit: 4 события, только success path, без secrets
4. ✅ No-secrets: все ответы чисты, нет tracebacks
5. ✅ Read-only: нет domain-data writes
6. ✅ Source boundaries: нет ClickHouse/Gateway/KSO/portal зависимостей
7. ✅ Compatibility: существующие endpoints нетронуты
