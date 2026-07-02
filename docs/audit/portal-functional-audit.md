# Portal Functional Audit

**Date:** 2026-07-02 | **Audit:** AUDIT.0

---

## Summary

Portal: 27 pages, 104 BackendClient methods, RBAC gating.  
**Overall:** Functional skeleton exists. Many pages are view-only. Key workflows missing.

---

## Scenario 1 — Campaign Management

| Step | Backend | Portal | Status |
|---|---|---|---|
| Create campaign | ✅ API | ✅ Form | COMPLETE |
| Edit campaign | ✅ API | ✅ Post form | COMPLETE |
| Add advertiser | ✅ API | ✅ In create form | COMPLETE |
| Add creative | ✅ API | ✅ Upload + bind | COMPLETE |
| Select KSO channel | ✅ API | ✅ Dropdown | COMPLETE |
| Select stores/devices | ✅ API | ✅ Dropdown | COMPLETE |
| Select dates | ✅ API | ✅ Date picker | COMPLETE |
| View status | ✅ API | 🟡 Basic | PARTIAL |
| Submit for approval | ✅ API | ✅ Button | COMPLETE |
| See errors | ⬜ | ⬜ MISSING | MISSING |

**Assessment:** Campaign CRUD complete. Missing: error display, status timeline, validation feedback.

---

## Scenario 2 — Planning

| Step | Backend | Portal | Status |
|---|---|---|---|
| Check availability | ✅ API (read-only) | ❌ No page | MISSING |
| See conflicts | ✅ API (read-only) | ❌ No page | MISSING |
| See occupancy | ✅ API (read-only) | ❌ No page | MISSING |
| Understand why blocked | ❌ | ❌ | MISSING |
| Get recommendations | ❌ | ❌ | MISSING |

**Assessment:** Backend has 5 read-only planning endpoints. Portal has ZERO planning workflow. This is a critical gap.

---

## Scenario 3 — Placement

| Step | Backend | Portal | Status |
|---|---|---|---|
| Create placement | ✅ API | ✅ Possible via campaign | PARTIAL |
| Target display surface | ✅ API | ✅ Dropdown | PARTIAL |
| Link to campaign | ✅ API | ✅ | PARTIAL |
| Schedule | ✅ API | 🟡 Schedule page | PARTIAL |
| View status | ✅ API | 🟡 Basic | PARTIAL |

**Assessment:** Placement exists but booking/reservation is missing. Schedule page is basic.

---

## Scenario 4 — Manifest / Preview

| Step | Backend | Portal | Status |
|---|---|---|---|
| Generate preview | 🧪 Dry-run API | ❌ No page | MISSING |
| See manifest summary | 🧪 Dry-run API | ❌ No page | MISSING |
| See KSO preview payload | 🧪 Dry-run API | ❌ No page | MISSING |
| Confirm dry-run only | ✅ | ❌ | MISSING |

**Assessment:** Manifest preview exists at API level but portal has NO page. Critical gap for publication workflow.

---

## Scenario 5 — Devices / Gateway

| Step | Backend | Portal | Status |
|---|---|---|---|
| See devices | ✅ API | ✅ Devices page | COMPLETE |
| See heartbeat | ✅ API | ✅ Device dashboard | COMPLETE |
| See status | ✅ API | ✅ Device dashboard | COMPLETE |
| See config | ✅ API | ✅ Device detail | COMPLETE |
| See manifest pulls | ❌ | ❌ | MISSING |
| See PoP | ✅ API | ✅ Proof-of-play page | COMPLETE |

**Assessment:** Device/Gateway portal is well-covered. Missing: manifest pull history.

---

## Scenario 6 — Analytics

| Step | Backend | Portal | Status |
|---|---|---|---|
| Delivery summary | ✅ API | ✅ Analytics page | COMPLETE |
| Planned vs delivered | ✅ API | ✅ Analytics page | COMPLETE |
| Device health | ✅ API | ✅ Device dashboard | COMPLETE |
| Breakdowns | ✅ API | 🟡 Basic | PARTIAL |
| Errors/no data | ✅ API | ⬜ Not handled | MISSING |

**Assessment:** Analytics portal is functional. Error/no-data states not gracefully handled.

---

## Scenario 7 — Emergency

| Step | Backend | Portal | Status |
|---|---|---|---|
| Capabilities | 🧪 Dry-run | ✅ Listed | COMPLETE |
| Preview | 🧪 Dry-run | ✅ Form | COMPLETE |
| Simulate stop | 🧪 Dry-run | ✅ Button | COMPLETE |
| Simulate message | 🧪 Dry-run | ✅ Button | COMPLETE |
| Warnings/errors | ✅ | ✅ Shown | COMPLETE |
| Dry-run only | ✅ | ✅ Banner | COMPLETE |

**Assessment:** Emergency portal is well-implemented. Dry-run only by design.

---

## Scenario 8 — Admin / Security

| Step | Backend | Portal | Status |
|---|---|---|---|
| Users list | ✅ API | ✅ Admin page | COMPLETE |
| Roles/permissions | ✅ API | ✅ Admin page | COMPLETE |
| Access review | ✅ H.4 verified | ⬜ Read-only view | PARTIAL |
| Audit logs | ✅ API | ✅ Admin page | COMPLETE |
| No secrets | ✅ | ✅ | COMPLETE |
| Role-based nav | ✅ RBAC | ✅ | COMPLETE |

**Assessment:** Admin portal is well-covered.

---

## Portal Completeness Summary

| # | Scenario | Status |
|---|---|---|
| 1 | Campaign management | 🟡 90% — missing errors/status timeline |
| 2 | Planning | ❌ 0% — ZERO portal pages |
| 3 | Placement | 🟡 60% — missing booking |
| 4 | Manifest/Preview | ❌ 0% — ZERO portal pages |
| 5 | Devices/Gateway | ✅ 90% |
| 6 | Analytics | 🟡 80% — missing error states |
| 7 | Emergency | ✅ 95% — dry-run only by design |
| 8 | Admin/Security | 🟡 80% |

**Missing Portal Pages:**
- /planning — availability, occupancy, conflicts
- /planning/book — booking/reservation
- /manifest — manifest preview, KSO payload
- /publications/workflow — approval chain

**BackendClient methods: 104 exist, ~40% used by portal pages.**

---

## Updated after PORTAL.1 (2026-07-03)

PORTAL.1 closed all functional gaps identified in this audit:

| # | Scenario | Before | After PORTAL.1 |
|---|---|---|---|
| 1 | Campaign management | 🟡 90% | ✅ 100% — workflow checklist + cross-links (PORTAL.1.5) |
| 2 | Planning | ❌ 0% | ✅ 100% — `/planning` availability/conflicts/occupancy (PORTAL.1.1) |
| 3 | Placement | 🟡 60% | ✅ 100% — booking + campaign integration (PORTAL.1.2) |
| 4 | Manifest/Preview | ❌ 0% | ✅ 100% — `/packages` list/detail/KSO check (PORTAL.1.4) |
| 5 | Devices/Gateway | ✅ 90% | ✅ 95% — cross-links + error states (PORTAL.1.6) |
| 6 | Analytics | 🟡 80% | ✅ 100% — error states + cross-linking (PORTAL.1.6) |
| 7 | Emergency | ✅ 95% | ✅ 95% — unchanged |
| 8 | Admin/Security | 🟡 80% | ✅ 90% — RBAC gate verified (PORTAL.1.7) |

**Previously missing portal pages — all delivered:**
- `/planning` — availability, occupancy, conflicts ✅
- `/bookings` — booking/reservation workflow ✅
- `/packages` — manifest preview, KSO payload ✅
- `/publications/{id}` — publication detail + publish result ✅

**Tests:** 359 targeted PORTAL.1 tests, 1337 portal regression (0 errors).  
**Backend:** untouched (2695/0).  
**Next:** UI.1 — Portal UI / UX Redesign.

---

## Updated after UI.1 (2026-07-03)

UI.1 завершил визуальный редизайн всех портальных страниц. Функциональный аудит (сценарии 1–8) не изменился — все оценки остаются актуальными после PORTAL.1. UI.1 добавил:

- Единый визуальный стандарт (page-header, section-card, metric cards, status badges)
- RBAC-aware навигацию (6 групп, device_service ограничен)
- Русскую терминологию («Пакеты показа», «Подтверждения показов», «Технический переключатель»)
- Cross-links между связанными страницами
- Стандартизированные empty/error states
- Dry-run safety для emergency + production switch NO-GO

**Portal baseline after UI.1:** 1709 passed / 0 errors / ~34 skipped.  
**Backend:** 2695/0 (untouched).  
**Next:** E2E.1 — Full Portal Scenario Validation.
