# HW Scanner E2E Validation Plan

**Date:** 2026-06-25
**Phase:** 38.15 — HW Scanner E2E Validation Plan
**Status:** 📋 POSTPONED / BLOCKED BY MISSING HARDWARE
**Commit:** TBD

---

## Executive Summary

HW scanner E2E validation is a 🔴 HIGH blocker for one-KSO pilot readiness.
This document defines the safe validation protocol in full readiness for execution,
but the validation **has NOT been executed**.

**Reason:** physical barcode scanner hardware is currently unavailable.
Validation can only resume when a real hardware scanner is attached to the test KSO.

**Status of this step:**
- HW scanner E2E validation: **NOT EXECUTED** ❌
- Pilot blocker: 🔴 HIGH — **remains active**
- Validation **cannot** be replaced by keyboard simulation
- Test can resume **only** when real hardware scanner is available

---

## 1. Why HW Scanner Validation Matters

The core value proposition of the Retail Media Platform is:

```
Physical barcode scan → Campaign match → Overlay render → PoP
```

Without verifying that:
1. A physical scanner input reaches UKM5 **without** being captured by the overlay
2. The active window remains UKM5 during scan
3. The first scan is not lost (no initialization race)
4. No focus steal occurs when the overlay is active

…we have **not proven** that the portrait overlay player is invisible to
UKM5 barcode input — the single most critical integration point.

**Previous attempt (38.1.11) was INCONCLUSIVE** — scanner was unavailable,
and a focus-loss defect was discovered and fixed (`restore_focus()` in commit
from 38.1.11.1). That fix has never been validated with a real scanner.

---

## 2. Current System State (pre-validation)

| Component | Status | Detail |
|---|---|---|
| Test KSO | ✅ running | 192.168.110.223, 768×1024 portrait |
| UKM5 (mint.service) | ✅ active | Production kiosk, PID tracked |
| Chromium kiosk | ✅ active | UKM5 fullscreen, PID tracked |
| Openbox | ✅ active | Window manager, PID tracked |
| Overlay player | ✅ proven (D3) | Portrait fullscreen 768×1024, click-through |
| `restore_focus()` | ✅ implemented | Post-rollback focus restoration |
| `focus_warning` stop reason | ✅ implemented | Safety catch |
| Scanner hardware | ❌ UNAVAILABLE | Physical device not present |
| D3 visual run | ✅ complete | 10s controlled, 13/13 stop criteria |

---

## 3. Safe Test Protocol

### 3.1 Approval Gate

```
PHASE_SCANNER_E2E_APPROVED
```

The test operator must explicitly provide this token before any scanner test begins.
**One controlled test only.** No repeated runs without re-approval.

### 3.2 Pre-Conditions

- [ ] Scanner physically connected to test KSO USB port
- [ ] UKM5 running normally (mint.service active, Chromium kiosk on :0)
- [ ] Overlay player profile registered (`portrait_fullscreen_idle_screensaver_768`)
- [ ] `restore_focus()` verified in code (commit from 38.1.11.1)
- [ ] Kill-switch file ready (`/run/verny/kso/kill_switch`)
- [ ] Operator physically present at KSO terminal
- [ ] VNC/SSH backup session ready (for remote stop if needed)
- [ ] Stop criteria checklist printed/visible

### 3.3 Test Procedure

**Phase S1 — Pre-scan baseline**

1. Verify UKM5 active: `DISPLAY=:0 xdotool getactivewindow getwindowname` → UKM5 window
2. Record UKM5 window ID: `xdotool getactivewindow`
3. Verify overlay runner NOT running
4. Scanner power-on and verify recognized by OS (`lsusb`, `dmesg | tail -20`)
5. Perform 1 scan on UKM5 idle screen → confirm UKM5 responds normally (operator observes)

**Phase S2 — Launch overlay**

6. Launch guarded runner with controlled timeout (e.g. 30s):
   ```
   DISPLAY=:0 PYTHONPATH=... python3 -m kso_player.cli.run_once \
       --profile portrait_fullscreen_idle_screensaver_768 \
       --timeout 30
   ```
7. Confirm overlay window visible (fullscreen green, 768×1024)
8. Confirm overlay window ID ≠ UKM5 window ID (via `xdotool getactivewindow`)

**Phase S3 — Scanner test (critical step)**

9. While overlay is active (green fullscreen), operator performs a **single physical scan** of a known barcode
10. Operator **visually observes** UKM5 screen response:
    - Does the barcode value appear in UKM5 input field?
    - Does UKM5 screen change (product lookup, etc.)?

**Phase S4 — Post-scan verification**

11. `xdotool getactivewindow` → window ID should still be UKM5 (same as Step 2)
12. `xprop -id <UKM5_WINDOW_ID> _NET_WM_STATE` → confirm focused
13. Let overlay timeout expire or trigger kill-switch
14. After rollback: verify UKM5 still active and responsive
15. Verify `restore_focus()` executed (check runner output for focus restoration log)

### 3.4 Safety Rules (ABSOLUTE)

| Rule | Description |
|---|---|
| **NO barcode logging** | Barcode value, scanner input, or key payload must never be printed, logged, or committed |
| **NO key payload logging** | Raw HID/keyboard scanner input must never be captured |
| **NO UKM5 DB access** | Do not read UKM5 database tables |
| **NO receipt/payment/fiscal/customer data** | Do not access any transactional data |
| **NO payment completion** | Do not complete any purchase transaction |
| **Operator-observed confirmation only** | Operator visually confirms UKM5 response — no automated data capture |
| **Screenshots allowed ONLY if no sensitive data visible** | If barcode, customer name, price, or personal data appears on screen, screenshots must be taken and then immediately deleted |
| **If sensitive data appears** | Stop test immediately, delete all screenshots, trigger kill-switch |

---

## 4. Expected Proof (what success looks like)

| # | Proof point | Verification method |
|---|---|---|
| P1 | **Overlay is active** (fullscreen green, 768×1024) | Operator visual or safe screenshot (no sensitive data) |
| P2 | **Active window remains UKM5** | `xdotool getactivewindow` returns UKM5 window ID |
| P3 | **Physical scanner input reaches UKM5** | Operator observes barcode appearing in UKM5 input field |
| P4 | **First scan is not lost** | Barcode registered on first trigger — no retry needed |
| P5 | **No focus steal** | `_NET_WM_STATE` shows UKM5 focused throughout overlay lifetime |
| P6 | **No barcode value stored** | Runner output, logs, and git diff contain zero barcode data |

---

## 5. Stop Criteria (immediate abort)

| # | Criterion | Action |
|---|---|---|
| S1 | **First scan lost** (UKM5 does not register barcode) | Kill-switch, investigate overlay window properties |
| S2 | **Overlay captures input** (barcode appears in overlay, not UKM5) | Kill-switch immediately |
| S3 | **Active window becomes overlay** (focus stolen from UKM5) | Kill-switch, check `restore_focus()` logic |
| S4 | **Need to read barcode/check/DB** to diagnose issue | STOP — use synthetic diagnosis only |
| S5 | **Any receipt/payment/fiscal/customer/card data appears** | Kill-switch, delete all screenshots immediately |
| S6 | **UKM5 instability** (crash, freeze, unexpected behavior) | Kill-switch, restore UKM5, report issue |
| S7 | **VNC/SSH loss** (operator cannot remote-stop) | Physical operator presses kill-switch or power-cycles |
| S8 | **CPU/RAM critical** (>90% CPU or <100MB RAM free) | Kill-switch, investigate resource leak |

---

## 6. Rollback Procedure

1. **Trigger kill-switch:** `touch /run/verny/kso/kill_switch`
2. **Wait:** overlay runner detects kill-switch within 1 second, exits cleanly
3. **Verify `restore_focus()`:** UKM5 window refocused, Chromium kiosk active
4. **Verify UKM5:** operator confirms normal UKM5 operation
5. **Delete evidence:** all screenshots with sensitive data → deleted
6. **Remove kill-switch:** `rm /run/verny/kso/kill_switch`
7. **Record:** UKM5 PID, Chromium PID, Openbox PID unchanged

---

## 7. What IS NOT This Test

| NOT this test | Why |
|---|---|
| Keyboard simulation of barcode | Keyboard input path is different from HID scanner path |
| Barcode scan in terminal/SSH | Must go through UKM5 input pipeline |
| Scanner test without overlay active | Does not prove overlay is transparent to scanner |
| UKM5 DB read for verification | Violates safety rule — operator visual confirmation only |
| UKM5 receipt/payment completion | Violates safety rule — no transactional data |
| Multiple scan attempts | One controlled test — if fails, diagnose, fix, re-approve |

---

## 8. Blockers That Remain

| # | Blocker | Status |
|---|---|---|
| B1 | **HW scanner E2E validation** | 🔴 POSTPONED — hardware unavailable |
| B2 | **Controlled long-run** (≥1 hour) | 🟡 NOT STARTED — safe to plan while scanner blocked |
| B3 | **BackendIntegration test isolation fix** | 🟡 NOT STARTED — safe to fix while scanner blocked |

---

## 9. Safe Alternatives While Scanner Unavailable

These actions are **safe** and **do not require scanner hardware**.
They reduce remaining blocker count and prepare for eventual pilot:

| # | Action | Status |
|---|---|---|
| A1 | **Controlled long-run plan** | Ready for 38.16 |
| A2 | **BackendIntegration test isolation fix** | Ready for 38.17 |
| A3 | **Pilot runbook update** | Ready for 38.18 |
| A4 | **Non-KSO documentation/regression work** | Always allowed |

**None of these alternatives substitute for scanner validation.**
The HW scanner blocker will remain 🔴 HIGH until real scanner test is executed.

---

## 10. Resumption Conditions

Test can resume when **ALL** of the following are true:

1. ✅ Physical barcode scanner is connected to test KSO (192.168.110.223)
2. ✅ Operator is physically present at KSO terminal
3. ✅ `PHASE_SCANNER_E2E_APPROVED` token issued
4. ✅ UKM5 running normally, KSO system unchanged from current state
5. ✅ Full regression green (baseline: ~4918 passed)
6. ✅ This document reviewed and stop criteria checklist printed

---

*Document created 2026-06-25 as part of 38.15 HW Scanner E2E Validation Plan.
No scanner test was executed. No KSO modifications made. No secrets, URLs,
tokens, barcodes, or personal data disclosed.*
