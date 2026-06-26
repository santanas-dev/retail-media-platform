# Pilot Readiness Gates Plan

**Phase:** 40.3 — Pilot Readiness Gates
**Date:** 2026-06-26
**Baseline:** commit `8ff648a` (40.2 — admin audit hardening)
**Regression:** 5124 passed, 32 skipped, 0 failed
**Status:** 📋 PLAN DOCUMENTED — **Gates NOT EXECUTED**

---

## Executive Summary

Retail Media Platform завершила архитектурный фундамент и hardening:

| Milestone | Status | Key Result |
|---|---|---|
| v0.9.0 — Product Portal Hardening | ✅ DONE | 4976 green, all demo removed |
| v0.10.0 — Approval/Publication Hardening | ✅ DONE | 5042 green, production workflow |
| 39.4 — Device/Sidecar Dashboard | ✅ DONE | 7 GAPs closed, dashboard live |
| 40.1 — RLS Hardening P0 | ✅ DONE | Gate closed, 42 endpoint tests |
| 40.2 — Admin Audit Hardening | ✅ DONE | 18 tests, payload redaction |
| Default regression | ✅ GREEN | 5124 passed, 32 skipped, 0 failed |

**Pilot readiness: CONDITIONAL ⚠️**

Physical pilot on 1 KSO requires closing the remaining gates below.
Scanner hardware unavailable. Controlled long-run not executed.
This document defines the exact gates, protocols, approval tokens, and decision criteria.

---

## 1. Current Readiness Summary

### 1.1 System State

| Component | Status | Detail |
|---|---|---|
| Backend (PostgreSQL) | ✅ | 22 migrations, 20+ routers, 47 permissions, 8 roles |
| Portal (server-side) | ✅ | 16 pages, all backend-driven, no JS/CDN/localStorage |
| KSO Player (768×1024) | ✅ | Portrait fullscreen X11, click-through, kill-switch, 2060 tests |
| KSO Sidecar Agent | ✅ | Manifest/media sync, agent_status, 1838 tests |
| KSO State Adapter | ✅ | 86 tests |
| Infra (KSO Linux) | ✅ | 227 tests |
| Device Gateway (JWT/bcrypt) | ✅ | Auth hardened, PoP/manifest secured |
| Campaign/Creative/Placement | ✅ | Code-based CRUD, creative binding |
| Schedule/Slot | ✅ | Production API, code-based |
| Approval Workflow | ✅ | Maker-checker, state machine |
| Publication Batch | ✅ | draft→pending_approval→approved→manifest_generated→published |
| Manifest Pipeline | ✅ | Unified builder, production endpoints |
| PoP Pipeline | ✅ | E2E: player→sidecar→backend→portal |
| Device Dashboard | ✅ | 8-table aggregation, readiness badges |
| RLS Enforcement | ✅ | All domains, 42 endpoint-level tests, gate closed |
| Audit Trail | ✅ | All critical workflows, payload redaction, 18 tests |

### 1.2 What is NOT Ready

| Item | Status | Priority |
|---|---|---|
| **HW scanner E2E** | 🔴 POSTPONED — scanner unavailable | P0 |
| **Controlled long-run** | 🔴 NOT EXECUTED — plan defined below | P0 |
| **Physical pilot approval** | 🟡 NOT GRANTED | N/A |
| Fleet rollout | ⬜ OUT OF SCOPE | — |
| mTLS/nonce/rate-limit | 🟡 DEFERRED | P1 |
| Sidecar daemon auto-start | 🟡 DEFERRED | P1 |
| Scanner SIMULATION | ⬜ FORBIDDEN | — |

### 1.3 Physical KSO State (UNCHANGED since D6)

| Item | Value |
|---|---|
| KSO IP | 192.168.110.223 |
| Display | 768×1024 portrait |
| UKM5 (mint.service) | Active, PID tracked |
| Chromium kiosk | Fullscreen on :0 |
| Openbox | Active |
| KSO agent root | `/home/ukm5/kso-agent/` |
| Agent config | `/home/ukm5/kso-agent/config/agent_config.json` |
| Device secret | `/home/ukm5/kso-agent/device_secret.dev` (600, value never printed) |
| Current manifest | `/home/ukm5/kso-agent/manifest/current_manifest.json` |
| Media cache | `/home/ukm5/kso-agent/media/current/` |
| Kill-switch | `/run/verny/kso/kill_switch` |
| Registry device_code | `test-dev-seed` |
| Sidecar daemon | NOT running |
| Overlay runner | NOT running |
| SSH/X11/Chromium | NOT launched |

---

## 2. Gate A — HW Scanner E2E Validation

**Status:** 🔴 POSTPONED — physical barcode scanner unavailable.
**Full validation plan:** `docs/audit/hw-scanner-e2e-validation-plan.md` (38.15)

### 2.1 Why This Gate Matters

The core value proposition:

```
Physical barcode scan → Campaign match → Overlay render → PoP
```

Without verifying that a physical scanner input reaches UKM5 without being captured by the overlay, we have NOT proven the single most critical integration point.

### 2.2 Why Keyboard Simulation is NOT Acceptable

| Aspect | Keyboard | HID Scanner |
|---|---|---|
| Input path | X11 key events → window focus | HID driver → raw device → application |
| Focus dependency | Depends on active window | Independent of X11 window focus |
| Timing | Programmable delay | Hardware-triggered, real-world latency |
| UKM5 input pipeline | Bypasses real pipeline | Goes through actual UKM5 input stack |

**The defect discovered in 38.1.11 (focus loss after rollback) can ONLY be confirmed resolved with real scanner input.**

### 2.3 Prerequisites

| # | Condition | Status |
|---|---|---|
| A1 | Physical barcode scanner connected to KSO USB port | ❌ (no hardware) |
| A2 | Operator physically present at KSO terminal | ❌ |
| A3 | UKM5 running normally (mint.service active) | ✅ |
| A4 | Overlay player profile registered | ✅ |
| A5 | `restore_focus()` verified in code (38.1.11.1) | ✅ |
| A6 | Kill-switch file ready | ✅ |
| A7 | VNC/SSH backup session ready | ❌ |
| A8 | Stop criteria checklist printed/visible | ❌ |
| A9 | Full regression green | ✅ |
| A10 | `PHASE_SCANNER_E2E_APPROVED` token issued | ❌ |

### 2.4 Approval Token

```
PHASE_SCANNER_E2E_APPROVED
```

Must be explicitly provided by the pilot operator before ANY scanner test.

### 2.5 Exact Allowed Actions

| # | Action | When |
|---|---|---|
| 1 | Verify scanner recognized by OS (`lsusb`, `dmesg`) | Pre-scan |
| 2 | Perform 1 scan on UKM5 idle (overlay OFF) — confirm UKM5 responds | Phase S1 |
| 3 | Launch guarded runner with controlled timeout (e.g. 30s) | Phase S2 |
| 4 | Perform 1 scan while overlay active — operator visually observes | Phase S3 |
| 5 | Verify active window still UKM5 after scan | Phase S4 |
| 6 | Let overlay timeout or trigger kill-switch | Phase S4 |

### 2.6 Exact Forbidden Actions

| # | Forbidden | Reason |
|---|---|---|
| F1 | Log, print, or commit barcode value | Safety rule — PII |
| F2 | Capture HID/keyboard scanner raw input | Safety rule |
| F3 | Read UKM5 database | Safety rule — transactional data |
| F4 | Access receipt/payment/fiscal/customer/card data | Safety rule — PII |
| F5 | Complete any purchase transaction | Safety rule |
| F6 | Automated data capture of UKM5 response | Operator visual confirmation only |
| F7 | Multiple scan runs without re-approval | One controlled test per approval |
| F8 | Keyboard simulation instead of physical scan | NOT equivalent |
| F9 | Scanner test without overlay active | Does not prove overlay transparency |

### 2.7 Expected Evidence

| # | Proof Point | Verification |
|---|---|---|
| P1 | Overlay active (fullscreen green, 768×1024) | Operator visual or safe screenshot |
| P2 | Active window remains UKM5 | `xdotool getactivewindow` = UKM5 window ID |
| P3 | Scanner input reaches UKM5 | Operator observes barcode in UKM5 field |
| P4 | First scan not lost | Single trigger → immediate UKM5 response |
| P5 | No focus steal | `_NET_WM_STATE` shows UKM5 focused |
| P6 | No barcode data stored | Runner output, logs, git diff — zero barcode |

### 2.8 Stop Criteria (Immediate Abort)

| # | Criterion | Action |
|---|---|---|
| S1 | First scan lost (UKM5 does not register) | Kill-switch, investigate |
| S2 | Overlay captures input | Kill-switch immediately |
| S3 | Active window becomes overlay | Kill-switch, check `restore_focus()` |
| S4 | Need to read barcode/check/DB to diagnose | STOP — synthetic diagnosis only |
| S5 | Any receipt/payment/fiscal/customer/card data appears | Kill-switch, delete all screenshots |
| S6 | UKM5 instability (crash/freeze) | Kill-switch, restore UKM5 |
| S7 | VNC/SSH loss | Physical operator abort |
| S8 | CPU/RAM critical (>90% CPU or <100MB RAM) | Kill-switch |

### 2.9 Rollback

1. `touch /run/verny/kso/kill_switch`
2. Wait: overlay runner exits within 1 second
3. Verify `restore_focus()` — UKM5 refocused
4. Operator confirms normal UKM5 operation
5. Delete all screenshots with sensitive data
6. `rm /run/verny/kso/kill_switch`
7. Record UKM5 PID, Chromium PID, Openbox PID unchanged

### 2.10 Resumption Conditions

Test can resume when **ALL** are true:

1. ✅ Physical barcode scanner connected to test KSO
2. ✅ Operator physically present at KSO terminal
3. ✅ `PHASE_SCANNER_E2E_APPROVED` token issued
4. ✅ UKM5 running normally, KSO system unchanged from current state
5. ✅ Full regression green
6. ✅ This document + scanner validation plan reviewed

---

## 3. Gate B — Controlled Long-Run

**Status:** 🔴 NOT EXECUTED — plan defined below.

D3 visual run was 10 seconds. Need proof the system is stable over realistic operational durations before any pilot.

### 3.1 Duration Options

| Option | Duration | Purpose | Recommendation |
|---|---|---|---|
| **Soak** | 1 hour | Technical soak — verify no memory leak, no heartbeat stall, no crash | ✅ Minimum for pilot confidence |
| **Working-Day** | 8 hours | Full working day simulation — multi-campaign cycling | 🟡 Recommended before pilot |
| **Pilot Readiness** | 48 hours | Weekend soak — multi-day stability, overnight idle | 🟡 Recommended before fleet |

**Recommendation:** Start with 1-hour technical soak. If green → 8-hour working-day. 48-hour only if stakeholder requires.

### 3.2 Monitoring Plan

| Metric | Source | Frequency | Alert Threshold |
|---|---|---|---|
| Backend health | `GET /health` (portal/backend) | Every 60s | 3 consecutive failures |
| Device heartbeat | `GET /api/device-dashboard` → heartbeat age | Every 60s | Age > 5 min |
| Sidecar status | Heartbeat → `sidecar_status` | Every 60s | warning/error |
| Manifest/media readiness | Dashboard → manifest_status + media_cache_status | Every 60s | missing/stale |
| PoP event queue | `GET /api/reports/pop` → last_event_at | Every 5 min | No events in 30 min (if campaign active) |
| Portal responsiveness | HTTP GET `/dashboard` | Every 5 min | >5s response or 5xx |
| Device dashboard | `GET /api/device-dashboard` | Every 5 min | readiness_badge=blocked |
| CPU | `mpstat` or equivalent | Every 5 min | >80% sustained 5 min |
| RAM | `free -m` | Every 5 min | <200MB free |
| Disk | `df -h` | Every 30 min | >90% full |
| Network | Ping backend | Every 60s | Packet loss >10% |
| Error count | `GET /api/device-dashboard` → errors | Every 5 min | New errors appearing |
| Retry count | Sidecar log | Every 10 min | Retries increasing |

### 3.3 What is Forbidden During Long-Run

| # | Forbidden | Reason |
|---|---|---|
| F1 | Changing UKM5 | Production POS system — immutable |
| F2 | autostart/systemd changes | Requires production hardening |
| F3 | Fleet rollout | Not approved for multi-KSO |
| F4 | Physical manifest delivery without approval | Separate gate |
| F5 | Live customer transactions | Not in scope |
| F6 | Scanner test | Separate gate (Gate A) |
| F7 | Deleting backend PoP evidence | Audit trail |

### 3.4 Approval Token

```
PHASE_LONG_RUN_APPROVED
```

Must be explicitly provided before ANY long-run begins.

Duration must be specified with the token (e.g. `PHASE_LONG_RUN_APPROVED:1h`).

### 3.5 Success Criteria

| # | Criterion | Threshold |
|---|---|---|
| C1 | Zero backend crashes or restarts | Duration |
| C2 | Zero heartbeat stalls > 5 min | Duration |
| C3 | Sidecar status never `error` | Duration |
| C4 | Device dashboard never `blocked` | Duration |
| C5 | Zero TCP connection failures between sidecar→backend | Duration |
| C6 | PoP events delivered (if campaign active) | Within SLA |
| C7 | CPU never sustained > 80% | Duration |
| C8 | RAM never < 200MB free | Duration |
| C9 | No disk exhaustion | Duration |
| C10 | No new errors in backend/portal logs | Duration |

### 3.6 Fail Criteria

| # | Criterion | Action |
|---|---|---|
| F1 | Backend crash | Kill-switch on KSO, diagnose backend, restart |
| F2 | Sidecar enters `error` state | Kill-switch, check sidecar log, fix, re-approve |
| F3 | Heartbeat stale > 5 min | Check sidecar/network, restart if safe |
| F4 | UKM5 instability | Kill-switch immediately, restore UKM5 |
| F5 | CPU/RAM critical | Kill-switch, investigate resource leak |
| F6 | Data loss (PoP events missing) | Stop, audit, do not resume without fix |

### 3.7 Rollback

1. `touch /run/verny/kso/kill_switch` (if runner active)
2. Stop sidecar agent if running
3. Verify UKM5 operational (operator confirmation)
4. Verify `restore_focus()` executed
5. Remove kill-switch
6. Record: duration reached, stop reason, metrics snapshot
7. Post-run report within 24 hours

---

## 4. Gate C — Pilot Runbook

**Status:** 🟡 PARTIAL — structure defined, content needs Gate A/B results.

Existing preflight documentation exists (D0–D6 docs, Phase A/B/C/D preflights). The pilot runbook must consolidate these into a single operator-facing document.

### 4.1 Runbook Structure

```
1. Roles and Responsibilities
   - Pilot operator (physical KSO access)
   - Backend operator (remote, portal access)
   - Security observer (audit log review)
   - Decision authority (go/no-go)

2. Communication Channel
   - Primary: [to be defined at pilot time]
   - Backup: [to be defined]
   - Escalation: [to be defined]

3. Pre-Check Checklist
   - Backend health + DB connectivity
   - Device heartbeat current (< 2 min)
   - Credential status: active, not expiring within 7 days
   - Manifest delivered and valid
   - Media cache complete
   - Kill-switch file present and writable
   - UKM5 operational
   - Operator physically present
   - Scanner connected and recognized (if Gate A done)
   - VNC/SSH backup ready
   - Stop criteria checklist printed/visible
   - Full regression green

4. Start Procedure
   - Activate monitoring (heartbeat watch, dashboard open)
   - Launch guarded runner (controlled timeout or campaign schedule)
   - Confirm overlay visible
   - Confirm active window = UKM5
   - Log start time, runner PID, UKM5 PID

5. Monitoring Procedure
   - Real-time dashboard (device-dashboard page)
   - Heartbeat watcher (age < 5 min)
   - Sidecar status watcher (must be running)
   - Error watcher (new device events)
   - Resource watcher (CPU/RAM/disk)
   - PoP event watcher (if campaign active)

6. Incident Response
   - Level 1: Warning (heartbeat stale 2-5 min) → investigate, no stop
   - Level 2: Degraded (sidecar warning, CPU > 70%) → prepare rollback
   - Level 3: Critical (heartbeat > 5 min, sidecar error, UKM5 instability) → kill-switch immediately

7. Stop Criteria (immediate abort)
   - Any Level 3 incident
   - Overlay captures UKM5 input
   - UKM5 instability (crash, freeze, unexpected behavior)
   - Any receipt/payment/fiscal/customer/card data appears
   - VNC/SSH loss with no physical operator
   - CPU/RAM critical

8. Rollback
   - Kill-switch activation
   - Verify UKM5 operational
   - Verify restore_focus()
   - Remove kill-switch
   - Post-mortem log collection

9. Evidence Collection
   - Backend audit log export (time window)
   - Device dashboard snapshot (start, middle, end)
   - Heartbeat timeline (age chart)
   - PoP event count (delta)
   - Resource usage snapshot
   - Operator notes (free text)
   - Screenshots (ONLY if no sensitive data)

10. Post-Run Report Template
    - Duration achieved
    - Stop reason (if not completed)
    - Metrics: heartbeats received, PoP events, errors, resource peaks
    - Issues encountered
    - Recommendations
    - Go/No-Go recommendation for next gate
```

### 4.2 Runbook Status

| Section | Status |
|---|---|
| Structure | ✅ Defined above |
| Content | 🟡 Needs Gate A/B results |
| Pre-check Checklist | ✅ Defined |
| Start/Monitor/Stop | ✅ Defined |
| Incident Response | ✅ Defined |
| Post-Run Template | ✅ Defined |
| **Full Runbook Document** | 🟡 To be created in `docs/audit/pilot-runbook.md` after Gate A/B |

---

## 5. Gate D — Go / No-Go Decision Matrix

### 5.1 Decision Criteria

| # | Criterion | Weight | Must Pass? |
|---|---|---|---|
| D1 | HW scanner E2E passed | P0 | YES — no pilot without scanner proof |
| D2 | Controlled long-run passed (≥1h) | P0 | YES — no pilot without stability proof |
| D3 | Default regression 100% green | P0 | YES |
| D4 | RLS gate closed | P0 | YES |
| D5 | Audit trail active (all domains) | P1 | YES |
| D6 | Device dashboard healthy | P1 | YES |
| D7 | Operator physically present | P0 | YES |
| D8 | Rollback prepared (kill-switch tested) | P1 | YES |
| D9 | Runbook reviewed and printed | P1 | YES |
| D10 | PHASE_SCANNER_E2E_APPROVED issued | P0 | YES |
| D11 | PHASE_LONG_RUN_APPROVED issued | P0 | YES |

### 5.2 Decision Outcomes

| Outcome | Condition | Meaning |
|---|---|---|
| **GO** ✅ | All P0 criteria met + all P1 criteria met | Pilot approved on 1 KSO |
| **CONDITIONAL GO** 🟡 | All P0 met, ≤2 P1 not met (with documented risk acceptance) | Pilot approved with documented caveats |
| **NO-GO** 🔴 | Any P0 criterion not met | Pilot NOT approved — fix blockers, re-submit |

### 5.3 Current Assessment (40.3 baseline)

| # | Criterion | Current Status |
|---|---|---|
| D1 | Scanner E2E | 🔴 NOT DONE (scanner unavailable) |
| D2 | Long-run | 🔴 NOT DONE |
| D3 | Regression green | ✅ 5124 passed |
| D4 | RLS gate closed | ✅ |
| D5 | Audit trail active | ✅ |
| D6 | Dashboard healthy | ✅ (pre-check at pilot time) |
| D7 | Operator present | ❌ (at pilot time) |
| D8 | Rollback prepared | ✅ (kill-switch + restore_focus) |
| D9 | Runbook reviewed | 🟡 (structure exists, final after Gate A/B) |
| D10 | Scanner token | ❌ |
| D11 | Long-run token | ❌ |

**CURRENT VERDICT: NO-GO 🔴**

Reason: D1 (scanner), D2 (long-run), D10 (scanner token), D11 (long-run token) not met as of 40.3.

---

## 6. Approval Tokens

Without the corresponding approval token, the following actions are **FORBIDDEN**:

| Token | Scope | Required For |
|---|---|---|
| `PHASE_SCANNER_E2E_APPROVED` | One controlled test | Physical scanner E2E validation (Gate A) |
| `PHASE_LONG_RUN_APPROVED` | Specified duration (1h/8h/48h) | Controlled long-run (Gate B) |
| `PHASE_PHYSICAL_KSO_ACCESS_APPROVED` | Specified session | Any SSH or physical access to KSO beyond read-only |
| `PHASE_MANIFEST_DELIVERY_APPROVED` | One delivery | Publishing manifest to physical KSO |
| `PHASE_SIDECAR_SYNC_APPROVED` | One sync | Sidecar media/manifest sync on physical KSO |
| `PHASE_POP_UPLOAD_APPROVED` | One upload | PoP event upload from physical KSO |
| `PHASE_SYSTEMD_AUTOSTART_APPROVED` | Permanent | Any systemd or autostart changes |

### Token Lifecycle

1. Token issued explicitly by decision authority
2. Token specifies scope and duration
3. Action executed (ONE controlled run)
4. Results reported
5. Token consumed (not reusable without re-issue)
6. No parallel tokens — one gate at a time

---

## 7. What Remains Out of Scope

**Explicitly NOT in scope for first pilot on 1 KSO:**

| Category | Items |
|---|---|
| **Fleet rollout** | Multi-KSO deployment, auto-scaling, fleet management |
| **Additional channels** | Android boxes, LED shelf banners, ESL labels |
| **Advanced analytics** | Charts, Excel export, BI drill-down, time-series graphs |
| **SSO/AD integration** | `auth_provider = 'local'` only |
| **MFA** | Not required for <10 users |
| **mTLS/nonce/rate-limit** | Device gateway hardening — post-pilot |
| **Credential rotation** | Manual management sufficient |
| **Systemd/autostart** | Manual startup only |
| **Physical UKM5 changes** | Vendor system — immutable |
| **Openbox/Chromium changes** | Vendor system — immutable |
| **Live customer transactions** | Not in scope |

---

## 8. Recommended Next Steps

| Step | What | Prerequisites | Status |
|---|---|---|---|
| **40.3.1** | HW scanner E2E | Scanner hardware + `PHASE_SCANNER_E2E_APPROVED` | 🔴 BLOCKED (no scanner) |
| **40.3.2** | Controlled 1h technical soak | `PHASE_LONG_RUN_APPROVED` + operator present | 🟡 Ready to execute |
| **40.3.3** | Pilot runbook finalization | Gate A/B results for real data | 🟡 After Gates A/B |
| **40.4** | v0.11.0 release tag | Gates A+B green + regression green | 🟡 After Gates A+B |

### Rationale for Ordering

1. Scanner E2E is P0 — no pilot without scanner proof. It's also the only hardware-dependent gate. Everything else can proceed in parallel.
2. Controlled long-run can execute immediately after approval — no hardware dependency.
3. Runbook finalized with real data from Gates A/B.
4. v0.11.0 tag as formal release gate after all criteria met.

---

## 9. Подтверждения (40.3)

- ❌ КСО не трогали
- ❌ SSH/X11/Chromium/runner не запускались
- ❌ Sidecar daemon не запускался
- ❌ PoP upload не выполнялся
- ❌ Manifest на физическую КСО не публиковался
- ❌ Sidecar sync не запускался
- ❌ Scanner test НЕ выполнялся
- ❌ Controlled long-run НЕ выполнялся
- ❌ UKM5/Openbox/systemd не менялись
- ❌ Secrets/full URLs/tokens/barcodes не выводились
- ❌ v0.9.0 и v0.10.0 tags не переписывались
- ✅ RLS gate остаётся closed
- ✅ Regression 5124 green (baseline from 40.2)

---

*Document created 2026-06-26 as part of 40.3 Pilot Readiness Gates Plan.*
*No physical actions executed. All gates remain NOT EXECUTED.*
*No secrets, full URLs, tokens, barcodes, or personal data disclosed.*
