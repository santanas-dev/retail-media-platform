# Project State After PORTAL.1.7

**Phase:** PORTAL.1.7 — Security / Regression Gate (gate-only)  
**Date:** 2026-07-02  
**Previous:** PORTAL.1.6 — Analytics / Error States / Cross-Linking (b772d14)

---

## PORTAL.1 Functional Pages — Complete

| Page | Route | Status |
|------|-------|--------|
| Планирование | `/planning` | ✅ PORTAL.1.1 |
| Бронирования | `/bookings` + detail | ✅ PORTAL.1.2 |
| Публикации | `/publications` + detail | ✅ PORTAL.1.3 |
| Пакеты показа | `/packages` + detail + KSO check | ✅ PORTAL.1.4 |
| Статус кампании | Campaign detail + workflow | ✅ PORTAL.1.5 |
| Аналитика/ошибки/связи | Analytics, PoP, Devices, Packages cross-links | ✅ PORTAL.1.6 |
| Security gate | RBAC, no-secrets, error safety, regression | ✅ PORTAL.1.7 |

## Security Verification

- **15 routes** с `require_auth_for_page` guards ✅
- **13 templates** проверены на secrets/traceback/CDN/scripts ✅
- `_safe_error()`: truncate 300 chars, no traceback, no raw JSON ✅
- Feature flag errors безопасны ✅
- Backend untouched ✅

## Remaining Gaps (documented)

1. Cross-links не RBAC-aware → UX improvement для UI.1
2. Nav links не RBAC-aware → UX improvement для UI.1
3. Confirm booking guard uses `bookings.read` (backend compensates)

## Current Baseline

- **Backend:** 2695 collected / 0 errors (не менялся)
- **Portal:** 1337 passed / 20 skipped / 0 failures
- **PORTAL.1 targeted:** all pass (1.1: 42, 1.2: 56, 1.3: 53, 1.4: 56, 1.5: 47, 1.6: 43, 1.7: 62)
- **Feature flags:** all default `False`
- **Production switch:** NO-GO

## Unstarted

- UI.1 (UI/UX redesign) — не начат
- E2E.1 — не начат
- KSO.1 (1 тестовый КСО) — не начат
- PROD.1 — не начат
- PILOT.1 — не начат
- Physical KSO test — блокирован

## Next Step

**PORTAL.1.8 — Closure Gate**
