# One-KSO Pilot Runbook

> **Status:** ✅ READY (docs only — physical execution pending)  
> **Date:** 2026-06-16  
> **Baseline:** HEAD `c389ba4` (42.4 Full Audit)  
> **Pilot:** 🔴 NO-GO (6 P0 blockers)  
> **Regression baseline:** 5355 passed, 44 skipped, 0 failed

---

## 1. Purpose

Validate Retail Media Platform backend product workflow on a single controlled physical KSO device — from creative upload through PoP ingestion. This runbook defines roles, gates, and execution phases. **It does NOT authorise physical execution** — each physical step requires its own approval token.

**Current status:** 🔴 NO-GO. Physical pilot impossible until all 6 P0 blockers closed.

---

## 2. Scope

| Parameter | Value |
|---|---|
| Devices | 1 (one) KSO — `test-dev-seed`, 192.168.110.223 |
| Display | 768×1024 portrait, UKM5 Chromium kiosk |
| Backend | 192.168.110.77:8421 |
| Portal | 192.168.110.77:8422 |
| Duration | Per-phase, max 48h for long-run |
| Fleet rollout | ❌ Explicitly excluded |
| Production traffic | ❌ No — controlled test only |

---

## 3. Roles & Responsibilities

| Role | Person / Designee | Responsibility |
|---|---|---|
| **Operator** | TBD | Physical KSO access, start/stop daemons, monitor |
| **Approver** | TBD (Сергей Пащенко or delegate) | Grant approval tokens, stop decision |
| **Observer** | TBD | Independent verification, evidence collection |
| **Rollback Owner** | TBD (Operator or dedicated) | Execute rollback if triggered |
| **Security Owner** | TBD | Audit trail, evidence integrity, secret hygiene |

**Rule:** No single person holds both Operator and Approver roles (maker-checker).

---

## 4. Prerequisites

All of the following must be confirmed before any physical step:

- [ ] `PHASE_SCANNER_E2E_APPROVED` token granted
- [ ] `PHASE_MANIFEST_DELIVERY_APPROVED` token granted
- [ ] `PHASE_SIDECAR_SYNC_APPROVED` token granted
- [ ] `PHASE_LONG_RUN_APPROVED` token granted
- [ ] `PHASE_PILOT_ROLLOUT_APPROVED` token granted
- [ ] Full regression green (5355+ tests)
- [ ] Backend & Portal running and healthy
- [ ] Physical KSO powered on, UKM5 in idle state
- [ ] Network: KSO (192.168.110.223) ↔ Backend (192.168.110.77:8421) reachable
- [ ] Rollback Owner identified and present
- [ ] Evidence collection tooling ready (screenshots, logs, timestamps)
- [ ] Stop criteria understood by all participants

---

## 5. Approval Gates

Each gate is a separate approval token. See `docs/runbooks/physical-approval-gates.md` for full details.

| # | Gate | Token | Current Status |
|---|---|---|---|
| 1 | Scanner E2E | `PHASE_SCANNER_E2E_APPROVED` | ❌ Pending |
| 2 | Manifest Delivery | `PHASE_MANIFEST_DELIVERY_APPROVED` | ❌ Pending |
| 3 | Sidecar Sync | `PHASE_SIDECAR_SYNC_APPROVED` | ❌ Pending |
| 4 | Long-Run | `PHASE_LONG_RUN_APPROVED` | ❌ Pending |
| 5 | Pilot Rollout | `PHASE_PILOT_ROLLOUT_APPROVED` | ❌ Pending |

**Rule:** Gates execute sequentially. Gate N+1 cannot start until Gate N completes successfully.

---

## 6. Pre-Check Checklist

Before any physical action, verify:

- [ ] Backend `/health` returns 200
- [ ] Portal `/reports` loads without errors
- [ ] Test campaign exists and is approved
- [ ] Test creative exists (768×1024 PNG/JPEG)
- [ ] Publication batch exists and is published
- [ ] Manifest generated (backend status: `published`)
- [ ] KSO network connectivity confirmed (ping 192.168.110.77)
- [ ] UKM5 is in idle state (no active scanner session, no receipt being processed)
- [ ] **UKM5 DB / receipts / payments / customer data NOT accessed or visible during any step**
- [ ] Chromium kiosk is running on UKM5 (expected state)
- [ ] Rollback procedure printed and accessible offline
- [ ] Communication channel established (Telegram/voice)

---

## 7. Execution Phases

### Phase 1: Scanner E2E

**Token required:** `PHASE_SCANNER_E2E_APPROVED`

| Step | Action | Expected Result | Evidence |
|---|---|---|---|
| 1.1 | Connect physical barcode scanner to KSO | Scanner recognised by UKM5 | Photo of scanner connected |
| 1.2 | Scan test barcode (campaign match) | UKM5 recognises barcode | Screenshot of UKM5 scan screen |
| 1.3 | Verify campaign creative renders | 768×1024 creative visible on screen | Photo of display |
| 1.4 | Verify PoP event generated | Event appears in `/api/reports/pop` | Backend log + portal screenshot |
| 1.5 | Scan non-matching barcode | Graceful fallback (no crash) | Screenshot |

**Stop criteria:**
- Scanner not recognised after 3 attempts → **STOP**
- UKM5 crashes or freezes → **STOP**
- PoP event not received within 60s → **STOP**

**⚠️ Keyboard simulation is NOT valid E2E.** Must use real barcode scanner hardware.

---

### Phase 2: Manifest Delivery

**Token required:** `PHASE_MANIFEST_DELIVERY_APPROVED`

| Step | Action | Expected Result | Evidence |
|---|---|---|---|
| 2.1 | Trigger manifest delivery from backend | Sidecar receives manifest | Sidecar log |
| 2.2 | Verify manifest parsed correctly | JSON valid, creative_refs populated | Manifest content (safe projection — no secrets) |
| 2.3 | Verify media files downloaded | Files present in cache directory | `ls -la` output (no file contents) |
| 2.4 | Verify manifest version matches backend | Version N in manifest = backend version | Log comparison |

**Stop criteria:**
- Manifest not received within 30s → **STOP**
- Manifest parse error → **STOP**
- Media download failed → **STOP** (check network/firewall)

---

### Phase 3: Sidecar Sync

**Token required:** `PHASE_SIDECAR_SYNC_APPROVED`

| Step | Action | Expected Result | Evidence |
|---|---|---|---|
| 3.1 | Start sidecar daemon | Process running, no crash | `systemctl status kso-sidecar` |
| 3.2 | Verify heartbeat sent | Backend receives heartbeat | Backend log |
| 3.3 | Verify PoP events uploaded | Events appear in `/api/reports/pop` | Portal screenshot |
| 3.4 | Stop sidecar gracefully | Process stops, no data loss | `systemctl stop kso-sidecar`, log check |

**Stop criteria:**
- Sidecar fails to start → **STOP**
- Heartbeat not received within 30s → **STOP**
- PoP events stuck → **STOP**

---

### Phase 4: Controlled Long-Run

**Token required:** `PHASE_LONG_RUN_APPROVED`

| Step | Action | Expected Result | Evidence |
|---|---|---|---|
| 4.1 | Start all daemons (player, sidecar, state-adapter) | All 3 running | `systemctl status` for each |
| 4.2 | Monitor for 48h minimum | No crashes, no memory leaks | Periodic screenshots, CPU/memory logs |
| 4.3 | Check at 1h, 6h, 12h, 24h, 48h | All daemons still running | Timestamped evidence |
| 4.4 | Verify PoP events continuous | No gaps > 5 min | Backend PoP timeline |
| 4.5 | Check disk usage | No runaway log growth | `df -h` output |

**Stop criteria:**
- Any daemon crashes → **STOP, investigate**
- Memory usage exceeds 80% of available → **STOP**
- Disk usage exceeds 80% → **STOP**
- PoP gap > 5 min → **STOP**
- UKM5 becomes unresponsive → **STOP**

---

### Phase 5: Pilot Rollout (Controlled)

**Token required:** `PHASE_PILOT_ROLLOUT_APPROVED`

| Step | Action | Expected Result | Evidence |
|---|---|---|---|
| 5.1 | Final GO/NO-GO decision | All prior gates passed | Signed approval |
| 5.2 | Deploy systemd units (enable) | Daemons auto-start on boot | `systemctl enable` output |
| 5.3 | Reboot KSO | All daemons restart automatically | `systemctl status` after reboot |
| 5.4 | Verify full cycle after reboot | Scan → render → PoP → backend | Full evidence chain |

**Stop criteria:**
- Daemons don't auto-start after reboot → **STOP**
- Any prior gate evidence invalidated → **STOP**

---

## 8. Stop Criteria (Global)

Any of the following triggers immediate STOP of the current phase and escalation to Rollback Owner:

- UKM5 becomes unresponsive or shows error dialog
- Chromium kiosk window disappears or shows error page
- Any daemon process terminates unexpectedly
- Backend `/health` returns non-200
- PoP event gap > 5 minutes
- Disk usage exceeds 80%
- Memory usage exceeds 80%
- **Any access to UKM5 receipts/payments/customer data observed**
- Operator or Observer calls STOP

---

## 9. Evidence Checklist

For each phase, collect:

- [ ] Timestamped screenshot of relevant screen
- [ ] Log excerpt (safe — no secrets, no barcodes, no customer data)
- [ ] Backend API response (safe projection only)
- [ ] Photo of physical setup (device + scanner)
- [ ] Operator notes (handwritten or digital)
- [ ] Observer confirmation (independent verification)

**Forbidden in evidence:**
- ❌ Barcode values / scanner output
- ❌ UKM5 receipt data / payment data / customer PII
- ❌ Backend URL, tokens, secrets, device_secret
- ❌ Manifest internal hashes / storage keys
- ❌ Full log files (only relevant excerpts)

---

## 10. Post-Run Checklist

After all phases complete (or STOP triggered):

- [ ] All daemons stopped gracefully
- [ ] UKM5 confirmed in normal idle state
- [ ] Evidence package assembled (no secrets)
- [ ] Observer report written
- [ ] Rollback report (if rollback executed)
- [ ] GO/NO-GO decision documented
- [ ] Pilot runbook updated with actual results
- [ ] Approval tokens status updated

---

## 11. NO-GO Conditions (Explicit)

Pilot remains NO-GO and MUST NOT proceed to any physical step if:

- Any P0 blocker unresolved (see `docs/audit/pilot-readiness-gap-register.md`)
- Required approval token NOT granted
- Rollback Owner NOT present
- UKM5 in active transaction (scanner session, receipt processing)
- Backend or Portal not healthy
- Full regression not green on current baseline
- Any participant raises safety concern

---

## 12. Safe Reporting Format

After pilot (or on STOP), produce a report with:

```
Pilot Date: YYYY-MM-DD
Operator: [name]
Observer: [name]
Baseline: [git commit hash]
Regression: [passed/skipped/failed]

Phases executed:
- [phase] → [PASS/FAIL/STOP]
- ...

Evidence: [list of files, no secrets]

Decision: GO / NO-GO
Reasons: [if NO-GO, specific blockers]

Next steps: [action items]
```

---

## 13. Reference Documents

- `docs/runbooks/kso-fallback-rollback-runbook.md` — Rollback procedures
- `docs/runbooks/physical-approval-gates.md` — Approval token definitions
- `docs/audit/pilot-readiness-gap-register.md` — Blocker status
- `docs/audit/technical-debt-register.md` — Full debt register
- `docs/audit/full-audit-42-4.md` — 42.4 audit findings
- `docs/pilot/one-kso-pilot-runbook.md` — Original pilot runbook (v0.12.0 baseline)
- `docs/pilot/go-no-go-checklist.md` — GO/NO-GO checklist
- `docs/pilot/evidence-checklist.md` — Evidence collection guide
- `docs/pilot/known-risks-and-deferred-items.md` — Known risks

---

> **⚠️ WARNING: This document describes planned procedures. NO physical actions are authorised by this document alone. Every physical step requires an explicit approval token granted by the designated Approver. Keyboard simulation does NOT replace HW scanner E2E. Fleet rollout is explicitly forbidden without separate approval.**
