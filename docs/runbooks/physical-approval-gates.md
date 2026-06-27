# Physical Approval Gates

> **Status:** ✅ Defined (all tokens PENDING)  
> **Date:** 2026-06-16  
> **Baseline:** HEAD `c389ba4` (42.4)  
> **Purpose:** Define individual approval tokens required for each physical pilot step

---

## Overview

Each physical action during the one-KSO pilot requires a separate approval token. Tokens must be granted sequentially — no token N+1 until token N is completed and evidence reviewed.

**Granting authority:** Designated Approver (Сергей Пащенко or delegate).  
**Revocation:** Any token can be revoked by Approver or Rollback Owner at any time.

---

## Token 1: PHASE_SCANNER_E2E_APPROVED

| Field | Value |
|---|---|
| **Status** | ❌ Pending |
| **What it authorises** | Connect physical barcode scanner to KSO; perform scan→render→PoP cycle |
| **What it does NOT authorise** | Manifest delivery, sidecar sync, long-run, fleet rollout; keyboard simulation; access to UKM5 DB |
| **Prerequisites** | Physical scanner hardware available; KSO accessible; UKM5 in idle state; Backend+Portal healthy; Full regression green; Pilot runbook reviewed |
| **Max duration** | 2 hours |
| **Stop criteria** | Scanner not recognised after 3 attempts; UKM5 crash/freeze; PoP event gap >60s; any data safety concern |
| **Rollback owner** | Designated before start |
| **Evidence required** | Photo of scanner connected; screenshot of scan screen (no barcode values visible); PoP event in backend `/api/reports/pop`; operator notes |
| **Forbidden data** | Barcode values; scanner output; UKM5 receipt/payment/customer data; backend URLs/tokens |
| **Regression before** | Full regression green on current baseline |
| **Regression after** | No new test failures; PoP event count incremented |
| **Operator presence** | Required — physical scanner connection |

---

## Token 2: PHASE_MANIFEST_DELIVERY_APPROVED

| Field | Value |
|---|---|
| **Status** | ❌ Pending |
| **What it authorises** | Trigger manifest delivery from backend; verify manifest received and parsed on KSO; verify media files downloaded |
| **What it does NOT authorise** | Sidecar sync, long-run, fleet rollout; rendering the manifest content (player already validated in test); modifying UKM5 |
| **Prerequisites** | PHASE_SCANNER_E2E_APPROVED completed + evidence reviewed; Published manifest exists in backend; KSO network reachable to backend:8421; Sidecar installed and configured |
| **Max duration** | 1 hour |
| **Stop criteria** | Manifest not received within 30s; parse error; media download failure; network timeout |
| **Rollback owner** | Designated before start |
| **Evidence required** | Sidecar log showing manifest receipt; manifest content (safe projection — no hashes/storage keys); file listing of cache directory; backend confirmation of delivery status |
| **Forbidden data** | Manifest internal hashes; storage keys; signed URLs; backend URL in evidence; UKM5 DB access |
| **Regression before** | Backend manifest tests green |
| **Regression after** | Manifest tests unchanged |
| **Operator presence** | Required — verify KSO filesystem |

---

## Token 3: PHASE_SIDECAR_SYNC_APPROVED

| Field | Value |
|---|---|
| **Status** | ❌ Pending |
| **What it authorises** | Start sidecar daemon on KSO; verify heartbeat; verify PoP events uploaded to backend; gracefully stop sidecar |
| **What it does NOT authorise** | Long-run, fleet rollout; leaving sidecar running unattended; enabling systemd auto-start |
| **Prerequisites** | PHASE_MANIFEST_DELIVERY_APPROVED completed; Sidecar configured with correct backend URL and device_secret; Backend reachable; systemd unit installed (not enabled) |
| **Max duration** | 1 hour |
| **Stop criteria** | Sidecar fails to start; heartbeat not received within 30s; PoP events stuck; unexpected daemon crash |
| **Rollback owner** | Designated before start |
| **Evidence required** | `systemctl status kso-sidecar`; backend heartbeat log; PoP events in `/api/reports/pop`; sidecar log (safe excerpts) |
| **Forbidden data** | Device secret; backend URL; access tokens; UKM5 DB |
| **Regression before** | Sidecar tests green (1838 passed) |
| **Regression after** | Sidecar tests unchanged |
| **Operator presence** | Required throughout |

---

## Token 4: PHASE_LONG_RUN_APPROVED

| Field | Value |
|---|---|
| **Status** | ❌ Pending |
| **What it authorises** | Start all 3 daemons; monitor for 48h minimum; collect periodic health evidence |
| **What it does NOT authorise** | Fleet rollout; unattended operation without monitoring; enabling systemd auto-start |
| **Prerequisites** | PHASE_SIDECAR_SYNC_APPROVED completed; All 3 daemons configured and tested individually; Monitoring plan documented; Disk space ≥20% free; Memory monitoring configured |
| **Max duration** | 48 hours (minimum) |
| **Stop criteria** | Any daemon crash; memory >80%; disk >80%; PoP gap >5 min; UKM5 unresponsive; any data safety concern |
| **Rollback owner** | Designated and available throughout 48h |
| **Evidence required** | Periodic screenshots at 1h/6h/12h/24h/48h; CPU/memory/disk logs at each checkpoint; PoP event timeline (no gaps); daemon uptime; operator log |
| **Forbidden data** | UKM5 transaction data; scanner output; customer PII; backend URLs in screenshots |
| **Regression before** | All P0 items (tokens 1-3) closed; full regression green |
| **Regression after** | Full regression green; no new failures |
| **Operator presence** | Periodic check-ins required (min every 6h); on-call for incidents |

---

## Token 5: PHASE_PILOT_ROLLOUT_APPROVED

| Field | Value |
|---|---|
| **Status** | ❌ Pending |
| **What it authorises** | Enable systemd auto-start for all 3 daemons; reboot KSO; verify auto-start on boot; final GO/NO-GO for controlled single-device pilot |
| **What it does NOT authorise** | Fleet rollout to multiple KSOs; production traffic; removing monitoring; disabling rollback capability |
| **Prerequisites** | PHASE_LONG_RUN_APPROVED completed + 48h evidence reviewed; All prior gate evidence validated; Rollback runbook finalised; Incident response plan ready; Stakeholder sign-off |
| **Max duration** | 4 hours |
| **Stop criteria** | Daemons don't auto-start after reboot; any prior gate evidence invalidated; Approver revokes GO |
| **Rollback owner** | Designated and present |
| **Evidence required** | `systemctl enable` output; `systemctl status` after reboot; full cycle proof (scan→render→PoP); final GO/NO-GO decision document |
| **Forbidden data** | Same as all prior tokens |
| **Regression before** | All P0 items closed; full regression green |
| **Regression after** | Full regression green |
| **Operator presence** | Required throughout |

---

## Token Lifecycle

```
[PENDING] → Approver grants → [ACTIVE] → Phase executes → [COMPLETED]
                                                  ↓
                                          STOP triggered → [REVOKED]
                                                  ↓
                                          Evidence reviewed → [COMPLETED] or [REVOKED]
```

---

## Revocation Rules

A token can be revoked if:
- Stop criteria triggered during execution
- Evidence review reveals issues
- New blocker discovered
- Approver or Rollback Owner calls revocation
- UKM5 safety concern arises

Revoked token returns to PENDING. Phase must be re-executed from start.

---

## Cross-Cutting Rules

| Rule | Applies to |
|---|---|
| No single person holds Operator + Approver | All tokens |
| Keyboard simulation ≠ scanner E2E | Token 1 |
| Evidence must not contain secrets/barcodes/PII | All tokens |
| UKM5 DB/receipts/payments/customers NEVER accessed | All tokens |
| Rollback Owner must be present or reachable | All tokens |
| Stop criteria are binding — no override | All tokens |
| Fleet rollout forbidden without Token 5 COMPLETED | Token 5 |

---

## Current Status Summary

| Token | Status | Blocker |
|---|---|---|
| PHASE_SCANNER_E2E_APPROVED | ❌ Pending | No physical scanner hardware |
| PHASE_MANIFEST_DELIVERY_APPROVED | ❌ Pending | Depends on Token 1 |
| PHASE_SIDECAR_SYNC_APPROVED | ❌ Pending | Depends on Token 2 |
| PHASE_LONG_RUN_APPROVED | ❌ Pending | Depends on Token 3 |
| PHASE_PILOT_ROLLOUT_APPROVED | ❌ Pending | Depends on Token 4 |

**Pilot remains NO-GO 🔴 until all 5 tokens completed.**
