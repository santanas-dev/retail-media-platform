# BACKEND.1.5 — Security / Regression Gate: QA Report

**Date:** 2026-07-03
**Status:** ✅ COMPLETE
**Git HEAD:** `0d33d20` (parent: BACKEND.1.4)
**Phase:** BACKEND.1 — Backend Debt Closure (FINAL GATE)

---

## Проверено

### Feature Flags
- Все 3 флага default `False`
- `_check_booking_writes_enabled()` → 422 до вызова сервиса
- `ENABLE_REAL_PUBLICATION` проверяется до `service.publish_batch()`
- `ENABLE_GENERATED_MANIFEST_WRITE` проверяется до создания GeneratedManifest

### Permissions
- `bookings.manage`, `bookings.read`, `bookings.approve` — разделение
- `publications.publish` — изолирован
- `device_service` исключён из обоих роутеров
- Нет wildcard `*` разрешений

### RLS
- `assert_object_in_advertiser_scope` в publication
- `resolve_user_scope_context` в publication
- `_resolve_batch_advertiser` связывает batch → advertiser

### GeneratedManifest
- Идемпотентность: SELECT перед INSERT
- `manifest_code = "pub-{batch_id}-{device_code}"` — стабилен
- FORBIDDEN_KEYS стрипят secrets из projection
- GM status = `"published"` только после publish

### Legacy KSO
- Endpoint читает `GeneratedManifest WHERE device_code=X AND status=published`
- `"no_manifest"` при отсутствии
- KSO adapter существует
- Device Gateway без изменений BACKEND.1.5

### Booking
- `_validate_capacity` для reserve/confirm
- `cancel_booking` → status `"cancelled"`, без `db.delete`
- Date validation: `date_from <= date_to`
- `exclude_booking_id` при перепроверке

### Publication
- Approval required (`ApprovalRequest`)
- Status gate: `manifest_generated` → `published`
- Нет `production_switch` в коде

### No-secrets
- Publication/Booking response schemas без secret-полей
- FORBIDDEN_KEYS в projection builder
- Router-файлы без hardcoded credentials

### Boundaries
- 0 миграций, 0 DDL, 0 Docker/.env
- Portal untouched
- No ClickHouse, no emergency execution, no destructive ops

---

## Tests

### BACKEND.1.5: 62/62 ✅
| Group | Count |
|---|---|
| Feature Flag Security | 7 |
| Permission Checks | 7 |
| RLS / Scope | 5 |
| GeneratedManifest Safety | 6 |
| Legacy KSO Compatibility | 5 |
| Booking Safety | 5 |
| Publication Safety | 5 |
| No-secrets / Audit | 6 |
| Source Boundaries | 10 |
| Regression | 6 |

### Full regression: 237/237 ✅
- BACKEND.1.5: 62
- BACKEND.1.4: 37
- BACKEND.1.3: 57
- BACKEND.1.1: 38
- BACKEND.1.2: 43

---

## Remaining Risks (documented, not blocking)

- Physical KSO test — 0 runs
- Production AV — disabled
- ClickHouse — not deployed
- mTLS — not implemented
- Real emergency execution — NO-GO

---

## Decisions

### GO/NO-GO for BACKEND.1.6 (Closure Gate)

**✅ GO**

BACKEND-фаза пройдена. Security gate подтверждает:
- Feature flags защищают все write-операции
- Permissions/RLS на месте
- No secrets, no production switch
- 237 тестов, 0 ошибок

Готово к закрытию BACKEND.1 и переходу к PORTAL.1.
