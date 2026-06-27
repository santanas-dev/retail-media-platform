# KSO Fallback & Rollback Runbook

> **Status:** ✅ READY (docs only — execution only after explicit approval)  
> **Date:** 2026-06-16  
> **Baseline:** HEAD `c389ba4` (42.4)  
> **⚠️ IMPORTANT:** All commands in this document are examples marked "execute only after explicit approval". Do NOT run them without an approved pilot phase.

---

## 1. Purpose

Define how to stop the Retail Media Platform daemons on a physical KSO and return the UKM5 to its normal operational state. This runbook is the single source of truth for rollback during pilot execution.

---

## 2. What Is an Incident

Any of the following during pilot execution:

| Incident Type | Examples |
|---|---|
| **Renderer failure** | Chromium window disappears, blank screen, rendering errors |
| **Daemon crash** | Player, sidecar, or state-adapter process terminates unexpectedly |
| **Network loss** | Backend unreachable from KSO, PoP events not delivered |
| **Resource exhaustion** | CPU >90%, memory >80%, disk >80% |
| **UKM5 interference** | UKM5 becomes slow, unresponsive, or shows error dialogs |
| **Data safety concern** | Any observation of UKM5 receipt/payment/customer data exposure |
| **Stop called** | Operator or Observer calls STOP per pilot runbook stop criteria |

---

## 3. Rollback Owner Authority

The **Rollback Owner** has sole authority to:
- Call STOP on any pilot phase
- Execute rollback procedures
- Override Operator if safety concern exists

The Rollback Owner **cannot** be overridden by Operator or Approver during an active incident.

---

## 4. Immediate STOP Procedure

If any incident detected:

### 4.1 Signal STOP

```
Operator: "STOP — [reason]"
Observer: "STOP acknowledged"
Rollback Owner: "Initiating rollback"
```

### 4.2 Stop Renderer (if running)

> **Execute only after explicit approval during pilot.**

```bash
# If Chromium was started by kso-player (systemd):
sudo systemctl stop kso-player

# Verify stopped:
systemctl status kso-player | grep Active
# Expected: Active: inactive (dead)
```

### 4.3 Stop Sidecar (if running)

> **Execute only after explicit approval during pilot.**

```bash
sudo systemctl stop kso-sidecar

# Verify stopped:
systemctl status kso-sidecar | grep Active
```

### 4.4 Stop State Adapter (if running)

> **Execute only after explicit approval during pilot.**

```bash
sudo systemctl stop kso-state-adapter

# Verify stopped:
systemctl status kso-state-adapter | grep Active
```

### 4.5 Verify All Stopped

```bash
# No Retail Media processes should be running:
ps aux | grep -E 'kso-player|kso-sidecar|kso-state|chromium.*retail' | grep -v grep
# Expected: no output
```

---

## 5. Return KSO to Normal State

### 5.1 Verify UKM5 is Active

```bash
# Check UKM5 Chromium kiosk is running (UKM5's own window, not our overlay):
ps aux | grep chromium | grep -v grep
# Expected: UKM5's own Chromium process visible

# Check UKM5 is focused (if X11 available):
# DISPLAY=:0 xdotool getactivewindow getwindowname
# Expected: UKM5 application window title
```

### 5.2 Verify No Residual Windows

```bash
# List all X11 windows (if X11 available):
# DISPLAY=:0 xdotool search --name ""
# No windows with titles containing "Retail Media" or "Portrait Overlay" should remain
```

### 5.3 Verify UKM5 Normal Operation

**Check (without accessing UKM5 DB):**
- UKM5 screen shows normal idle/transaction UI
- No error dialogs
- UKM5 responds to touch/keyboard input
- **Do NOT attempt to process a transaction — observe only**

---

## 6. Evidence Collection (Safe)

During/after rollback, collect:

### 6.1 Screenshots

```bash
# Capture current screen state (if X11 available):
# DISPLAY=:0 import -window root /tmp/rollback-evidence-$(date +%Y%m%d-%H%M%S).png
```

**⚠️ Ensure NO barcode, receipt, payment, or customer data is visible in screenshot.**

### 6.2 Logs

```bash
# Capture last 50 lines of daemon logs (if journald available):
# sudo journalctl -u kso-player -n 50 --no-pager > /tmp/rollback-player.log
# sudo journalctl -u kso-sidecar -n 50 --no-pager > /tmp/rollback-sidecar.log

# Capture system resource snapshot:
# free -h > /tmp/rollback-memory.txt
# df -h > /tmp/rollback-disk.txt
# uptime > /tmp/rollback-uptime.txt
```

**⚠️ Redact any secrets, tokens, backend URLs, or device_secret from logs before including in evidence package.**

### 6.3 Incident Report

Document:
```
Time: [HH:MM:SS]
Incident: [description]
Trigger: [which stop criterion]
Actions taken: [steps 4.1–4.5]
Result: [KSO state after rollback]
UKM5 status: [normal / needs attention]
Evidence files: [list]
```

---

## 7. What NOT to Do

| ❌ Forbidden | Reason |
|---|---|
| Kill UKM5 Chromium process | UKM5's own kiosk — NOT our player. Killing it breaks UKM5 operation |
| Access UKM5 database | Contains receipts, payments, customer PII |
| Modify UKM5 configuration | `.profile`, `xinitrc`, Openbox config — not our files |
| Delete Retail Media files without approval | Evidence may be needed for post-mortem |
| Run `reboot` without Rollback Owner approval | May lose evidence, may disrupt UKM5 |
| Run `systemctl disable` without approval | Remove auto-start — requires separate approval |
| Access scanner output / barcode data | Sensitive retail data |
| Take screenshots with UKM5 transaction data visible | PII / fiscal data exposure |

---

## 8. What Can Be Safely Removed (with approval)

Only after Rollback Owner approval and evidence collection:

| Item | Command | Condition |
|---|---|---|
| Player cache | `rm -rf /var/cache/kso-player/media/*` | After evidence collected |
| Sidecar state | `rm -f /var/lib/kso-sidecar/state.json` | After PoP events confirmed sent |
| Temp logs | `rm -f /tmp/rollback-*.txt` | After evidence package assembled |

**Do NOT remove:**
- Systemd unit files (`/etc/systemd/system/kso-*.service`)
- Environment files (`/etc/kso/*.env`)
- Daemon binaries
- Evidence package

---

## 9. Safe Communication Template

Use this format when reporting incidents:

```
[PILOT INCIDENT]
Time: HH:MM
KSO: test-dev-seed (192.168.110.223)
Phase: [1-5]
Incident: [one-line description]
Stop criterion: [which one triggered]
Action: STOP called, rollback initiated
UKM5: [normal / attention needed]
Next: [awaiting rollback completion / investigation]
```

**Do NOT include in communication:**
- Backend URLs
- Token values
- Device secrets
- Barcode data
- UKM5 transaction details
- Customer information

---

## 10. Post-Rollback Verification

After rollback complete, confirm:

- [ ] All 3 daemons stopped (`systemctl status` shows inactive)
- [ ] UKM5 Chromium kiosk running normally
- [ ] UKM5 responsive to input
- [ ] No Retail Media windows visible on display
- [ ] Evidence package assembled (no secrets)
- [ ] Incident report written
- [ ] Rollback Owner sign-off

---

## 11. Decision After Rollback

| UKM5 State | Decision |
|---|---|
| Normal, no impact | Pilot can resume after root cause fixed |
| Degraded but functional | Pilot paused — investigate, GO decision required |
| Unresponsive / crashed | Pilot ABORTED — escalate to UKM5 support, do NOT restart pilot |

---

## 12. Escalation

If UKM5 is affected:

1. **Do NOT attempt to fix UKM5** — this is retail production equipment
2. Contact UKM5 administrator (Сергей Пащенко)
3. Provide incident report (safe format only)
4. Await UKM5 recovery before any further pilot actions

---

## 13. Reference

- `docs/runbooks/one-kso-pilot-runbook.md` — Pilot execution phases and stop criteria
- `docs/runbooks/physical-approval-gates.md` — Approval token definitions
- `docs/pilot/known-risks-and-deferred-items.md` — Known risks reference

---

> **⚠️ WARNING: All commands in this document are marked "execute only after explicit approval during pilot." This runbook does NOT authorise any physical action. Commands are examples of what would be run IF and WHEN the relevant pilot phase is approved and active. Running them without approval violates pilot governance.**
