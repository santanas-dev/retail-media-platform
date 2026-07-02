# TZ Compliance Matrix

**Date:** 2026-07-02 | **Audit:** AUDIT.0

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | READY — full implementation |
| 🟡 | PARTIAL — implemented but incomplete |
| 👁️ | READ_ONLY — API exists, no write capability |
| 🧪 | DRY_RUN — preview/simulation only |
| ❌ | MISSING — not implemented |
| ⏸️ | DEFERRED — design gate exists, not implemented |
| 🔴 | BLOCKED — blocked by dependency |

---

## Identity / RBAC / RLS

| Feature | Status | Notes |
|---|---|---|
| User CRUD | ✅ | Full API + portal admin |
| Role management | ✅ | 8 roles in seed |
| Permission system | ✅ | 51 permissions |
| RLS enforcement | ✅ | advertiser/store/channel scope |
| Service accounts | ✅ | device_service |
| Audit trail | ✅ | All security events logged |
| Seed idempotency | ✅ | on_conflict_do_nothing |

---

## Channel Registry

| Feature | Status | Notes |
|---|---|---|
| Channel types | ✅ | 5 device types seeded |
| Capability profiles | ✅ | 6 profiles |
| Physical devices | ✅ | external_code + properties |
| Logical carriers | ✅ | | 
| Display surfaces | ✅ | |

---

## Campaigns & Creatives

| Feature | Status | Notes |
|---|---|---|
| Campaign CRUD | ✅ | Full API + portal forms |
| Creative upload | ✅ | + ffprobe validation |
| Creative moderation | ✅ | approve/reject/rework |
| AV scanning | 🟡 | NoScanner in dev, real AV deferred |
| Campaign-placement link | ✅ | |
| Campaign submit | ✅ | |
| Campaign approval workflow | 🟡 | API exists, portal partial |

---

## Planning / Inventory

| Feature | Status | Notes |
|---|---|---|
| Inventory units | 👁️ | Read-only API |
| Capacity rules | 👁️ | Read-only |
| Availability check | 👁️ | 5 read-only endpoints |
| Occupancy | 👁️ | Read-only |
| Conflict detection | 👁️ | Read-only |
| Booking/reservation | ❌ | NOT IMPLEMENTED |
| Booking approval | ❌ | NOT IMPLEMENTED |
| Placement scheduling | 🟡 | API exists, booking missing |

---

## Publications / Manifest

| Feature | Status | Notes |
|---|---|---|
| Publication batch | 🧪 | Dry-run only |
| Publication approval | 🧪 | Dry-run only |
| Real publish | ❌ | NO-GO — design gate |
| Universal Manifest V1 | 🧪 | Preview mode |
| KSO adapter | 🧪 | Dry-run only |
| Manifest generation | 🧪 | Not writing GeneratedManifest |
| Manifest delivery | 🧪 | Preview only |

---

## Device Gateway

| Feature | Status | Notes |
|---|---|---|
| Device auth/token | ✅ | |
| Heartbeat | ✅ | |
| Manifest pull (universal) | 🧪 | Preview only |
| PoP ingestion | ✅ | Legacy + enterprise |
| Media delivery | ✅ | |
| Device lifecycle | ✅ | register/block/unregister |
| Rate limiting | ✅ | In-memory (H.4) |
| mTLS | ⏸️ | Deferred |

---

## Analytics / PoP

| Feature | Status | Notes |
|---|---|---|
| PoP normalization | ✅ | KSO + Gateway |
| Delivery aggregation | ✅ | 14 metrics |
| Analytics API | 👁️ | 4 read-only endpoints |
| Portal analytics | ✅ | |
| ClickHouse pipeline | ⏸️ | Deferred |
| CSV export | ✅ | |

---

## Emergency

| Feature | Status | Notes |
|---|---|---|
| Capabilities | 🧪 | Dry-run |
| Preview | 🧪 | Dry-run |
| Simulate stop | 🧪 | Dry-run |
| Simulate message | 🧪 | Dry-run |
| Real emergency execution | ⏸️ | NO-GO — design gate |
| Emergency portal page | 🧪 | Dry-run only |
| Permission (emergency.read) | ✅ | 3 roles |

---

## Observability

| Feature | Status | Notes |
|---|---|---|
| /api/health/live | ✅ | |
| /api/health/ready | ✅ | |
| /api/health/dependencies | ✅ | Admin-only |
| /api/health/metrics | ✅ | Prometheus-text |
| Correlation ID | ✅ | X-Correlation-ID |
| Structured logging | ✅ | JSON to stdout |
| Security headers | ✅ | 9 headers |
| Prometheus deployed | 🟡 | Configs ready, not deployed |
| Grafana deployed | 🟡 | Specs ready, not deployed |
| Alert rules | 🟡 | 9 rules ready, not loaded |

---

## Security

| Feature | Status | Notes |
|---|---|---|
| Rate limiting | ✅ | 4-tier, in-memory |
| CORS | ✅ | SafeCORSMiddleware |
| No-secrets | ✅ | All layers verified |
| Access review | ✅ | H.4 verified |
| HTTPS | ❌ | Not deployed |
| HSTS | ❌ | Requires HTTPS |
| CSP | ❌ | Pending UI gate |

---

## Ops

| Feature | Status | Notes |
|---|---|---|
| Backup scripts | ✅ | 3 scripts (--dry-run + --help) |
| Restore scripts | ✅ | CONFIRM_RESTORE guarded |
| Deploy preflight | ✅ | |
| Rollback preflight | ✅ | |
| Backup/restore drill | 🟡 | Protocol ready, not executed |
| RPO/RTO defined | 🟡 | Targets set, not measured |

---

## KSO Physical

| Feature | Status | Notes |
|---|---|---|
| KSO device available | 🟡 | Hardware exists (192.168.110.223) |
| Physical playback test | 🔴 | NEVER EXECUTED |
| Chromium kiosk test | 🔴 | NEVER EXECUTED |
| Screen verified | 🔴 | NOT VERIFIED |
| PoP from KSO | 🔴 | NOT VERIFIED |
| Rollback tested | 🔴 | NOT TESTED |
| Emergency on KSO | 🔴 | NOT TESTED |

---

## Summary

| Category | Ready | Partial | Read-Only | Dry-Run | Missing | Deferred | Blocked |
|---|---|---|---|---|---|---|---|
| Identity/RBAC | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| Channels | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| Campaigns/Creatives | 6 | 1 | 0 | 0 | 0 | 0 | 0 |
| Planning/Inventory | 0 | 1 | 4 | 0 | 2 | 0 | 0 |
| Publications/Manifest | 0 | 0 | 0 | 7 | 1 | 0 | 0 |
| Device Gateway | 5 | 0 | 0 | 1 | 0 | 1 | 0 |
| Analytics/PoP | 3 | 0 | 1 | 0 | 0 | 1 | 0 |
| Emergency | 1 | 0 | 0 | 5 | 0 | 1 | 0 |
| Observability | 6 | 3 | 0 | 0 | 0 | 0 | 0 |
| Security | 4 | 0 | 0 | 0 | 3 | 0 | 0 |
| Ops | 4 | 2 | 0 | 0 | 0 | 0 | 0 |
| KSO Physical | 0 | 1 | 0 | 0 | 0 | 0 | 6 |
| **TOTAL** | **41** | **8** | **5** | **13** | **6** | **3** | **6** |
