# Pilot Readiness Gap Register — 43.5

**Date:** 2026-06-16  
**Baseline:** HEAD (43.5 — Business Demo Acceptance)  
**Pilot Status:** 🔴 NO-GO (5 physical blockers, 1 doc blocker RESOLVED)  
**Business Demo:** ✅ Backend-only scenario ready for demonstration via `/readiness` page

---

## Blockers (P0)

### B-01: HW Scanner E2E Validation

| Field | Value |
|---|---|
| Status | ❌ Not executed |
| Evidence | Scanner hardware absent during all test phases |
| Attempted | Keyboard simulation (not valid for E2E) |
| Risk | Scanner integration may fail on real hardware |
| Resolution Gate | Physical barcode scanner connected to UKM5, full scan→manifest→render→PoP cycle |
| Dependencies | Physical KSO + scanner hardware |
| Notes | `keyboard simulation` is NOT valid E2E — must use real scanner |
| Safe Execution | Requires physical presence at KSO location |

### B-02: Controlled 48h+ Long-Run

| Field | Value |
|---|---|
| Status | ❌ Not executed |
| Evidence | No long-run monitoring data collected |
| Attempted | Short smoke tests only (<10 min) |
| Risk | Memory leaks, disk full, Chromium crash, daemon restart loops |
| Resolution Gate | 48h+ continuous run with monitoring (CPU, memory, disk, daemon health) |
| Dependencies | All P0 KSO items closed, monitoring infrastructure ready |
| Notes | Must run on physical KSO, not simulator |
| Safe Execution | Start daemons, enable logging, monitor for 48h, collect evidence |

### B-03: Manifest Delivery to Physical KSO

| Field | Value |
|---|---|
| Status | ❌ Not approved |
| Evidence | No manifest ever delivered to physical KSO |
| Attempted | Local manifest generation only |
| Risk | Network/firewall may block backend access from KSO network |
| Resolution Gate | Successful manifest fetch + parse + media download on physical KSO |
| Dependencies | Physical KSO with network access to backend:8421 and MinIO |
| Notes | Backend URL must be reachable from KSO subnet (192.168.110.x) |
| Safe Execution | Configure KSO network, test connectivity, deliver one manifest |

### B-04: Sidecar Sync Physical Start

| Field | Value |
|---|---|
| Status | ❌ Not executed |
| Evidence | No sidecar daemon running on physical KSO |
| Attempted | Local daemon smoke tests only |
| Risk | systemd may not start daemons, port conflicts, permission issues |
| Resolution Gate | `systemctl start kso-sidecar` succeeds, PoP events reach backend |
| Dependencies | Physical KSO, systemd units deployed (D-IN-01), backend accessible |
| Notes | Must verify PoP events are received by backend `/api/reports/pop` |
| Safe Execution | Deploy systemd, start sidecar, verify backend receives events |

### B-05: Pilot Runbook / Fallback / Rollback Finalization

| Field | Value |
|---|---|
| Status | ✅ RESOLVED (42.5) |
| Evidence | `docs/runbooks/one-kso-pilot-runbook.md`, `docs/runbooks/kso-fallback-rollback-runbook.md`, `docs/runbooks/physical-approval-gates.md` |
| Resolution | Three runbooks created: pilot execution, fallback/rollback, approval gates. All 5 approval tokens defined. |
| Notes | Doc-only resolution. Physical execution still requires token grants. |

### B-06: Live Pilot / Fleet Rollout Approval

| Field | Value |
|---|---|
| Status | ❌ Not approved |
| Evidence | No approval from stakeholders |
| Resolution Gate | All P0 + P1 items closed, GO decision from pilot review |
| Dependencies | All other blockers resolved |

---

## Pre-Pilot Gaps (P1)

### G-01: Manifest Delivery Validation

| Field | Value |
|---|---|
| Status | ⚠️ Not validated |
| Description | Manifest delivery gate approval pending — B-03 |
| Risk | Manifest may not parse on KSO |
| Resolution | Execute B-03 + verify manifest content on KSO filesystem |

### G-02: Sidecar Sync Validation

| Field | Value |
|---|---|
| Status | ⚠️ Not validated |
| Description | Sidecar sync not physically validated — B-04 |
| Risk | PoP events may not reach backend |
| Resolution | Execute B-04 + verify PoP events in backend |

### G-03: Offline / Degraded Mode

| Field | Value |
|---|---|
| Status | ⚠️ Not implemented |
| Description | No graceful degradation when backend unreachable |
| Risk | Sidecar may spam retries, exhaust resources |
| Resolution | Add exponential backoff + circuit breaker (D-KS-05) |

### G-04: Rollback Runbook

| Field | Value |
|---|---|
| Status | ⚠️ Missing |
| Description | No documented procedure to roll back a failed pilot |
| Risk | Cannot recover from pilot failure |
| Resolution | Create `docs/pilot/rollback-runbook.md` (D-IN-02) |

### G-05: Security Hardening Plan

| Field | Value |
|---|---|
| Status | ⚠️ Missing |
| Description | No dedicated security hardening document |
| Risk | Incomplete security posture for production |
| Resolution | Create `docs/security/hardening-plan.md` (D-DC-01) |

---

## 42.3 Regression Check

**Question:** Did 42.3 (Planned Reports Export) introduce any new blockers?

**Answer:** No.

| Check | Result |
|---|---|
| CSV export leakage | ✅ No secrets/tokens/backend URL in CSV |
| Advertiser anonymization | ✅ Conflicts anonymized, device_code=*** |
| Reports RLS | ✅ `reports.read` enforced, `resolve_user_scope_context()` |
| Publication/manifest workflow | ✅ Unchanged, no regression |
| Portal UX | ✅ No JS/CDN/localStorage, GET-only exports |
| test-kso legacy | ✅ Not increased, not decreased |
| Full regression | ✅ 5355 passed, 44 skipped |

---

## Approval Tokens (unchanged from v0.12.1)

| Token | Status |
|---|---|
| PHASE_SCANNER_E2E_APPROVED | ❌ Pending |
| PHASE_LONG_RUN_APPROVED | ❌ Pending |
| PHASE_PHYSICAL_DELIVERY_APPROVED | ❌ Pending |
| PHASE_SIDECAR_SYNC_APPROVED | ❌ Pending |
| PHASE_RUNBOOK_APPROVED | ❌ Pending |
| PHASE_ROLLBACK_APPROVED | ❌ Pending |
| PHASE_FLEET_ROLLOUT_APPROVED | ❌ Pending |

---

## Next Steps

1. **Unblock physical access** — all 6 blockers require physical KSO presence
2. **Close P1 items** — rollback runbook, security hardening, offline mode
3. **Schedule test-kso cleanup sprint** (43.x) — 171 refs, 20 P2 items
4. **Execute pilot gates sequentially**: scanner → delivery → sidecar → long-run → rollback → approval

**Pilot remains NO-GO 🔴 until all 6 blockers resolved.**
