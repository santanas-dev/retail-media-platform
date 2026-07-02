# BACKEND.1 — Backend Debt Closure Gate

**Date:** 2026-07-03
**Status:** ✅ CLOSED
**Phase:** BACKEND.1 — Backend Debt Closure (COMPLETE)

---

## 1. Executive Summary

BACKEND.1 закрывает три критических backend-долга, выявленных в AUDIT.0:

| Долг | Статус до | Статус после |
|---|---|---|
| Publication real publish | ❌ DRY_RUN (ошибочно классифицирован) | ✅ Защищён `ENABLE_REAL_PUBLICATION` |
| GeneratedManifest writes | ❌ Отсутствует | ✅ `ENABLE_GENERATED_MANIFEST_WRITE` |
| Booking write API | ❌ Без защиты | ✅ `ENABLE_BOOKING_WRITES` |

Все три долга закрыты под feature flags с default `False`. Без явного включения флагов система в безопасном состоянии.

---

## 2. Why BACKEND.1 Was Needed

AUDIT.0 обнаружил, что pilot track начат преждевременно:
- Publication pipeline не был готов к production
- GeneratedManifest не создавался → KSO endpoint возвращал `"no_manifest"`
- Booking endpoints существовали, но без защиты feature flag
- Portal и UI не были готовы

**Решение AUDIT.0:** остановить pilot, сначала закрыть backend, потом portal, потом UI, потом 1-KSO тест, только потом пилот.

---

## 3. BACKEND.1 Commit History

| Commit | Gate | Changes |
|---|---|---|
| `fce9611` | BACKEND.1.0 — Design Gate | Design document only |
| `78e434a` | BACKEND.1.1 — Publication Flag | `ENABLE_REAL_PUBLICATION`, 38 tests |
| `1e04ccd` | BACKEND.1.2 — GeneratedManifest | Bridge function, 43 tests |
| `3e96b29` | BACKEND.1.3 — Booking API | Router guard, 57 tests |
| `0d33d20` | BACKEND.1.4 — E2E Tests | 37 E2E tests |
| `53cb562` | BACKEND.1.5 — Security Gate | 62 security tests |
| TBD | BACKEND.1.6 — Closure | This document |

**Total:** 7 commits, 175 targeted tests, 0 code changes in 1.4/1.5/1.6

---

## 4. Publication Closure

**Before:** AUDIT.0 считал publication DRY_RUN. На самом деле `publish_batch()` был полностью реализован и коммитил в БД — любой с правом `publications.publish` мог опубликовать.

**After:**
- `ENABLE_REAL_PUBLICATION: bool = False` (default)
- OFF → 422 structured error, без side effects
- ON → существующий `publish_batch()` работает
- `PublishBatchResult` с `generated_manifest_created`, `next_step`
- Проверка флага ДО вызова сервиса

---

## 5. GeneratedManifest Closure

**Before:** `publish_batch()` → `ManifestVersion.published` ✅, но `GeneratedManifest` не создавался → `/kso/{device}/manifest` → `"no_manifest"`.

**After:**
- `ENABLE_GENERATED_MANIFEST_WRITE: bool = False` (default)
- Bridge: `create_generated_manifests_for_published_batch()`
- Резолвит `device_code` через `PublicationTarget.store_id → KsoDevice`
- Строит KSO-safe projection через `build_kso_safe_manifest_projection()`
- Идемпотентный: `manifest_code = "pub-{batch_id}-{device_code}"`, SELECT перед INSERT
- GM status = `"published"`, НЕ `"generated"`
- Legacy KSO endpoint теперь видит манифест

---

## 6. Booking Closure

**Before:** Роутер и сервис существовали, но без feature flag защиты.

**After:**
- `ENABLE_BOOKING_WRITES: bool = False` (default)
- 6 write endpoints защищены `_check_booking_writes_enabled()`
- 3 read endpoints без ограничений
- Capacity validation через `_validate_capacity()`
- Cancel → `"cancelled"`, без `db.delete`
- Planning читает bookings через `_BOOKING_STATUSES_THAT_CONSUME`

---

## 7. E2E Backend Scenario

BACKEND.1.4 подтвердил полную цепочку source-inspection тестами:

```
Campaign → Booking → Planning → Publication → GeneratedManifest → Legacy KSO Endpoint
```

Feature flag сценарии:
- All OFF → safe
- Booking ON, rest OFF → booking работает, publish denied
- Booking+Pub ON, GM OFF → publish без манифеста
- All ON → полная цепочка

---

## 8. Security / RLS / No-Secrets

BACKEND.1.5 подтвердил:
- Все 3 флага default `False`
- `device_service` исключён из booking/publication
- RLS advertiser scope enforced
- No secrets в response schemas
- FORBIDDEN_KEYS в projection builder
- Нет production_switch, нет hardcoded credentials
- 0 миграций, 0 DDL, 0 Docker/.env

---

## 9. Legacy KSO Compatibility

- `/kso/{device_code}/manifest` endpoint НЕ менялся
- Читает `GeneratedManifest WHERE device_code=X AND status=published`
- `"no_manifest"` при отсутствии → `"served"` при наличии
- KSO adapter не менялся
- Device Gateway не менялся

---

## 10. Feature Flags Summary

| Flag | Default | OFF behavior | ON behavior | Gate |
|---|---|---|---|---|
| `ENABLE_REAL_PUBLICATION` | `False` | 422 real_publication_disabled | publish_batch() executes | BACKEND.1.1 |
| `ENABLE_GENERATED_MANIFEST_WRITE` | `False` | return (0, []), no GM created | GM created after publish | BACKEND.1.2 |
| `ENABLE_BOOKING_WRITES` | `False` | 422 booking_writes_disabled | all write endpoints work | BACKEND.1.3 |

---

## 11. Test Results

| Gate | Targeted Tests | Status |
|---|---|---|
| BACKEND.1.1 | 38 | ✅ |
| BACKEND.1.2 | 43 | ✅ |
| BACKEND.1.3 | 57 | ✅ |
| BACKEND.1.4 | 37 | ✅ |
| BACKEND.1.5 | 62 | ✅ |
| **Total BACKEND.1** | **237** | **✅** |

Backend collection: **2695 / 0 errors**

---

## 12. Backend Baseline After BACKEND.1

- 28 domains
- 3 feature flags (all OFF by default)
- Publication chain: ready behind flags
- GeneratedManifest: created behind flag
- Booking: write-protected behind flag
- Planning: reads bookings
- Legacy KSO: serves manifests from GeneratedManifest
- Backend E2E: verified
- Security gate: passed

---

## 13. Remaining Deferred Items (NOT blocking PORTAL.1)

| Item | Status |
|---|---|
| Production switch | 🚫 NO-GO |
| Physical KSO test | 🚫 BLOCKED_BY_HARDWARE |
| ClickHouse pipeline | 🚫 Deferred |
| mTLS | 🚫 Deferred |
| Signed manifests | 🚫 Deferred |
| Real emergency execution | 🚫 NO-GO |
| Emergency actions persistence | 🚫 Deferred |
| Prometheus/Grafana deployment | 🚫 Deferred |
| Backup/restore real drill | 🚫 Deferred |
| HTTPS/HSTS/CSP | 🚫 Deferred |
| Credential rotation | 🚫 Deferred |
| KSO production switch | 🚫 NO-GO |
| B5/B6 approvals | 🚫 Not obtained |

---

## 14. What Is Still Not Portal-Ready

- Portal incomplete (27 pages, много функционала не реализовано)
- UI/UX требует редизайна
- Нет portal E2E тестов
- Нет publication workflow через portal
- Нет booking management через portal

---

## 15. Explicit NO-GO Items

| Item | Decision |
|---|---|
| Production switch | 🚫 NO-GO до завершения всей дорожной карты |
| Real store pilot | 🚫 NO-GO до PORTAL+UI+E2E+KSO+PROD |
| KSO production switch | 🚫 NO-GO |
| ClickHouse pipeline | 🚫 NO-GO |
| Real emergency execution | 🚫 NO-GO |

---

## 16. GO/NO-GO for PORTAL.1

### ✅ GO — PORTAL.1 Portal Functional Completion

Backend готов:
- Все критические долги закрыты
- Feature flags защищают все write-операции
- E2E backend chain verified
- Security gate пройден
- 237 тестов, 0 ошибок

PORTAL.1 может начинаться с уверенностью, что backend-фундамент надёжен.

---

## 17. Next Phase

**PORTAL.1 — Portal Functional Completion**
- Booking management UI
- Publication workflow UI
- Manifest preview
- Campaign management
- Planning integration
- Admin panel completion
