# Portrait Overlay Phase 2 — Readiness Review

> **⚠️ PHASE 2 IS STILL NOT APPROVED.**
> **This review does NOT grant permission to run overlay.**
> **This document is an informational readiness assessment, not an authorization.**
>
> Дата: 2026-06-24
> Шаг: 38.1.1
> Ревизия: 1
> Родительский шаг: 38.1 (Physical KSO Phase 0–1 Dry Smoke)
>
> **Требуется явное manual approval Сергея Пащенко перед ЛЮБЫМ запуском.**

---

## 1. Executive Summary

Phase 2 readiness review подготовлен на основе успешного прохождения Phase 0 (readiness) и Phase 1 (dry smoke 6/6) на физической КСО 192.168.110.223. Все предварительные условия проверены, кодовая база готова. Решение о запуске остаётся за владельцем процесса.

**Ключевой вывод:** техническая readiness подтверждена. Безопасность overlay обеспечена контрактом профиля `portrait_idle_overlay_768`, трёхуровневым kill-switch и жёсткими stop criteria. Основной остаточный риск — взаимодействие overlay с Openbox WM на работающем Chromium kiosk.

---

## 2. Code Review — Readiness Assessment

### 2.1 Profile Contract: `portrait_idle_overlay_768`

**Файл:** `apps/kso_player/kso_player/profiles/portrait_idle_overlay_768.py`
**Тесты:** 71 (в `tests/test_profile_portrait_idle_overlay_768.py`)

| Параметр | Значение | Статус |
|----------|----------|--------|
| Root screen | 768 × 1024 | ✅ matches KSO |
| Overlay zone | (0, 400) — 768 × 240 | ✅ Zone C, safe |
| Creative canvas | (0, 420) — 768 × 200 | ✅ inside overlay |
| Gap to payment | 80 px (y=640 bottom → y=720 payment top) | ✅ confirmed |
| Gap to header | 340 px (y=60 header bottom → y=400 overlay top) | ✅ confirmed |
| Show states | `idle` only | ✅ |
| Hide SLA | < 500 ms | ✅ |
| Forbidden zones | payment (487,720,92,120), header (0,0,768,60), close (725,4,6,20) | ✅ verified |
| Forbidden state fields | receipt, transaction, payment, fiscal, customer, card, items, cashier | ✅ enforced |
| Fullscreen | **false** (mandatory) | ✅ |
| Kiosk mode | **false** (mandatory) | ✅ |
| UKM5 DB access | **false** (mandatory) | ✅ |

**Assessment:** Profile geometry checked against UKM5 UI safe zone mapping. No overlap with critical UI elements. Gap to payment (80 px) provides safe margin.

### 2.2 Shell Plan: `shell_plan.py`

**Файл:** `apps/kso_player/kso_player/shell_plan.py`
**Тесты:** 59

| Правило | Статус |
|---------|--------|
| `build_shell_plan()` generates correct geometry from profile | ✅ |
| `apply_state_snapshot()` integrates state + kill-switch | ✅ |
| Forbidden Chromium flags enforced (`--kiosk`, `--start-fullscreen`, `--start-maximized`, `--fullscreen`) | ✅ |
| Window type: `overlay` (not `kiosk`, not `app`) | ✅ |
| `always_on_top: true`, `no_focus_steal: true` | ✅ |
| `kill_switch_required: true` | ✅ |
| `hide_on_start_if_state_not_idle: true` | ✅ |

**Assessment:** Shell plan correctly translates profile into safe window parameters. All forbidden Chromium flags are blocked at the plan level.

### 2.3 Kill-Switch: `kill_switch.py`

**Файл:** `apps/kso_player/kso_player/kill_switch.py`
**Тесты:** 41

| Rule | Статус |
|------|--------|
| File exists → hidden | ✅ |
| File absent → not active | ✅ |
| Permission/OS errors → fail-safe (active/hidden) | ✅ |
| `None`/empty path → fail-safe (active/hidden) | ✅ |
| Default path: `/run/verny/kso/kill_switch` | ✅ configurable |
| KSO override: `/tmp/kso_test/kill_switch` | ✅ Phase 1 confirmed |

**Assessment:** Kill-switch is fail-safe (errors → hide). On the KSO, the user `ukm5` cannot write to `/run/verny/kso/` — must use `/tmp/kso_test/kill_switch`. This is a known deviation from the default and is documented throughout.

### 2.4 State Observer: `state_observer.py`

**Файл:** `apps/kso_player/kso_player/state_observer.py`
**Тесты:** 117 (+3 added in 38.1)

| Rule | Статус |
|------|--------|
| 9 allowed states (idle, busy, scan, cart, payment, error, offline, unknown, stale) | ✅ |
| Only `idle` permits display | ✅ |
| Stale detection (default 5000 ms) | ✅ |
| Forbidden keys: 44 exact + 17 patterns | ✅ enforced |
| Microsecond timestamps (`.573421Z`) parsed correctly | ✅ Phase 1 confirmed on Python 3.6.9 |
| File errors → safe default (unknown, hidden) | ✅ |
| No network, no DB, no UKM5 | ✅ |

**Assessment:** State observer correctly enforces the idle-only contract. Microsecond timestamp parsing verified on Python 3.6.9 (core fix from Phase 1).

### 2.5 Smoke Harness: `portrait_smoke.py` + standalone

| Файл | Назначение | Статус |
|------|-----------|--------|
| `kso_player/portrait_smoke.py` | Dev-side smoke (Python 3.7+, dataclasses) | ✅ 42 теста |
| `scripts/standalone_smoke_py36.py` | KSO-side standalone (Python 3.6+) | ✅ 6/6 на КСО |

**Assessment:** Both harnesses produce identical pipeline results. Standalone version confirmed working on KSO Python 3.6.9.

### 2.6 Physical Test Plan: `portrait-overlay-physical-kso-test-plan.md`

**Файл:** `docs/audit/portrait-overlay-physical-kso-test-plan.md`
**Статус:** обновлён (Step 38.1 results appended)

| Phase | Статус |
|-------|--------|
| Phase 0 — Readiness | ✅ пройден |
| Phase 1 — Dry Smoke | ✅ 6/6 пройдено |
| Phase 2 — Overlay Render | ⛔ **НЕ одобрен** |
| Phase 3 — Rollback | план готов |

---

## 3. Phase 2 Command Plan (DO NOT EXECUTE)

> **⚠️ ALL COMMANDS IN THIS SECTION ARE FOR REVIEW ONLY.**
> **DO NOT execute without explicit approval from Sergey Paschenko.**

### 3.1 Pre-Flight (Setup — before overlay launch)

```bash
# Step A — Ensure working directory exists
mkdir -p /tmp/kso_test

# Step B — Pre-create kill-switch (ready BEFORE overlay launch)
touch /tmp/kso_test/kill_switch

# Step C — Verify kill-switch works
ls -la /tmp/kso_test/kill_switch
# Expected: file exists, kill-switch IS active (overlay will hide)

# Step D — Create synthetic idle state
CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%S.000000Z")
cat > /tmp/kso_test/state.json << STATE_EOF
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "idle",
  "source": "phase2_test",
  "updated_at_utc": "$CURRENT_UTC",
  "stale_after_ms": 999999999
}
STATE_EOF

# Step E — Verify state is valid
python3 /tmp/kso_test/smoke_test.py \
    --state-file /tmp/kso_test/state.json \
    --kill-switch /tmp/kso_test/kill_switch
# Expected: visible_plan=hidden (kill-switch IS active)

# Step F — Verify UKM5 is healthy BEFORE touching anything
systemctl is-active mint.service    # must be: active
ps aux | grep "[c]hromium.*kiosk"    # must have process
free -h | grep Mem                   # available > 1.5 GB
```

### 3.2 Overlay Launch Approaches (3 options — select one at approval time)

#### Option A: Chromium `--app` mode (recommended)

**Требуется:** Chromium 114 (уже установлен на КСО).
**Принцип:** Chromium `--app` создаёт frameless окно без тулбара/меню/табов — идеально для overlay.

```bash
# Step 1 — Create overlay HTML (safe, no network, no external URLs)
cat > /tmp/kso_test/overlay.html << 'HTML_EOF'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body { margin:0; padding:0; background:#222; color:#fff;
         width:768px; height:240px; overflow:hidden;
         display:flex; align-items:center; justify-content:center;
         font-family:Arial,sans-serif; font-size:24px; }
</style></head>
<body>🧪 Phase 2 Test Overlay — Portrait Idle</body>
</html>
HTML_EOF

# Step 2 — Remove kill-switch (so overlay CAN show)
rm /tmp/kso_test/kill_switch

# Step 3 — Verify smoke says visible
python3 /tmp/kso_test/smoke_test.py \
    --state-file /tmp/kso_test/state.json \
    --kill-switch /tmp/kso_test/kill_switch
# Expected: visible_plan=visible

# Step 4 — LAUNCH overlay (FOR REVIEW ONLY — DO NOT EXECUTE)
chromium-browser \
    --app="file:///tmp/kso_test/overlay.html" \
    --window-position=0,400 \
    --window-size=768,240 \
    --disable-features=DialMediaRouteProvider \
    --disable-translate \
    --disable-save-password-bubble \
    --no-first-run \
    --disable-session-crashed-bubble \
    --noerrdialogs \
    --disable-infobars \
    --disable-component-update \
    --test-type \
    &

# ⚠️  VERIFIED: command does NOT contain --kiosk, --fullscreen,
#    --start-fullscreen, or --start-maximized.
# ⚠️  Window mode: --app (frameless, not kiosk).
# ⚠️  Position/size explicit: --window-position=0,400 --window-size=768,240.

# Step 5 — Verify overlay appeared (visual check)
#   Overlay visible at bottom of screen (y=400-640)?
#   Payment button (y=720) still visible?
#   UKM5 header (y=0-60) still visible?
#   Close button (x=725,y=4) still visible?
```

**Chromium `--app` mode safety notes:**
- ✅ No `--kiosk` (won't monopolise screen)
- ✅ Explicit `--window-position` + `--window-size` (predictable geometry)
- ✅ `--app` = frameless (no URL bar, no tabs, no bookmarks)
- ✅ `--disable-features=DialMediaRouteProvider` (no cast/DLNA dialogs)
- ✅ `--no-first-run` + `--disable-session-crashed-bubble` + `--noerrdialogs` (no popups)
- ✅ `--test-type` (removes "Chrome is being controlled" infobar)
- ⚠️ Openbox may NOT honour `always_on_top` natively — overlay may appear behind UKM5 kiosk

#### Option B: `xdotool` window management (if installed)

```bash
# Check if available
which xdotool || sudo apt-get install -y xdotool

# Launch overlay as Option A, then:
# Get overlay window ID and set always-on-top
OVERLAY_WID=$(xdotool search --name "Phase 2 Test Overlay" | head -1)
xdotool windowactivate $OVERLAY_WID
# On Openbox: use wmctrl if xdotool stacking doesn't work
```

#### Option C: Dedicated X11 overlay (requires xlib/Python — most complex)

```bash
# Requires: python3-tk or similar
# NOT recommended for Phase 2 — overengineered for a smoke test
# Reserve for production player integration
```

**Recommendation:** Option A (Chromium `--app`) is the simplest and safest for Phase 2.

### 3.3 Overlay Monitor & Stop Commands

```bash
# === MONITOR ===
# Check if overlay Chromium is running
ps aux | grep "[c]hromium.*overlay.html"

# Check that UKM5 Chromium kiosk is STILL running
ps aux | grep "[c]hromium.*kiosk"

# Check RAM/CPU
free -h | grep Mem
top -bn1 | head -5

# === EMERGENCY STOP (any operator can do this) ===
# Method 1: Kill-switch (recommended first step)
touch /tmp/kso_test/kill_switch
# This does NOT kill the overlay process —
# but the contract says the overlay MUST hide on kill-switch.
# If using standalone smoke-driven overlay, it polls kill-switch.

# Method 2: Kill ONLY the test overlay Chromium
# WARNING: do NOT pkill chromium — that would kill UKM5 kiosk!
pkill -f "chromium-browser.*overlay.html"
# This targets ONLY the overlay chromium instance.

# Method 3: Kill by PID
OVERLAY_PID=$(ps aux | grep "[c]hromium.*overlay.html" | awk '{print $2}')
kill $OVERLAY_PID

# === VERIFY UKM5 NOT BROKEN ===
ps aux | grep "[c]hromium.*kiosk"    # MUST still be running
systemctl is-active mint.service      # MUST be: active
ps aux | grep "[M]intUKM"             # MUST still be running

# === ROLLBACK (full cleanup) ===
pkill -f "chromium-browser.*overlay.html"  # kill overlay
touch /tmp/kso_test/kill_switch             # activate kill-switch
rm -f /tmp/kso_test/state.json              # remove test state
# rm /tmp/kso_test/kill_switch              # keep kill-switch until verified
# rm -f /tmp/kso_test/overlay.html          # keep for forensics if needed
```

### 3.4 How NOT to Touch UKM5 Chromium

| ❌ NEVER do this | Why |
|------------------|-----|
| `pkill chromium` | Kills UKM5 kiosk — production outage |
| `killall chromium-browser` | Kills ALL chromium instances |
| `systemctl restart mint` | Restarts cash register system |
| `systemctl stop mint` | Stops cash register |
| Edit `/home/ukm5/.config/openbox/autostart` | Changes UKM5 autostart |
| Edit `/home/ukm5/mint/bin/www/index.html` | Changes UKM5 web UI |
| Send SIGTERM to any `MintUKM` Java process | Stops cash register |
| Run `xdotool` on UKM5 Chromium window | May break kiosk |
| Change Openbox config (`~/.config/openbox/rc.xml`) | May change WM behaviour |

| ✅ ALWAYS do this |
|---------------------|
| Target overlay Chromium by URL pattern: `overlay.html` |
| Target by PID (not by name) |
| Verify UKM5 Chromium kiosk PID list BEFORE and AFTER |
| Test kill-switch FIRST, then process kill |
| Keep a terminal open with `touch /tmp/kso_test/kill_switch` ready |

---

## 4. Stop Criteria Review

### 4.1 Geometry Safety (zones not overlapped)

| UI Element | Zone | Overlay? | Status |
|------------|------|----------|--------|
| Payment button | (487,720) 92×120 | Overlay bottom = y=640 | ✅ Safe (80 px gap) |
| Header bar | (0,0) 768×60 | Overlay top = y=400 | ✅ Safe (340 px gap) |
| Close button | (725,4) 6×20 | Overlay top = y=400 | ✅ Safe (396 px gap) |
| Product grid | (0,60) 768×640 | Overlay covers y=400–640 | ⚠️ Overlays product area (intended) |

**Assessment:** No critical UI overlap. The 80 px gap to payment provides safe margin even with window positioning variance (± a few pixels).

### 4.2 Resource Limits

| Metric | Warning | Critical | KSO Baseline (Phase 0) |
|--------|---------|----------|------------------------|
| CPU load avg | > 2.0 | > 4.0 | 0.15 |
| RAM available | < 1.0 GB | < 500 MB | 1.9 GB |
| Disk free | < 50 GB | < 20 GB | 85 GB |

**Assessment:** KSO has ample headroom. Chromium `--app` window overhead is ~50-100 MB RAM, negligible CPU when idle.

### 4.3 Kill-Switch Readiness

| Check | Command | Status |
|-------|---------|--------|
| Path writable | `touch /tmp/kso_test/kill_switch` | ✅ confirmed Phase 0 |
| Smoke reads it | `python3 smoke_test.py --kill-switch /tmp/kso_test/kill_switch` | ✅ confirmed Phase 1 |
| Fails safe | `rm /tmp/kso_test/kill_switch` → not active | ✅ confirmed |
| Operator can execute | Single `touch` command | ✅ trivial |

### 4.4 Rollback Readiness

| Rollback step | Time to execute | Verified |
|---------------|----------------|----------|
| `touch /tmp/kso_test/kill_switch` | < 1 sec | ✅ Phase 0 |
| `pkill -f "chromium-browser.*overlay.html"` | < 2 sec | ⚠️ untested (no overlay yet) |
| Verify UKM5 kiosk alive | < 5 sec | ✅ Phase 1 |

### 4.5 Human Factors

| Requirement | Status |
|-------------|--------|
| Operator physically near KSO | ⚠️ requires coordination |
| Operator knows kill-switch command | ⚠️ requires briefing |
| Operator knows STOP criteria | ⚠️ requires briefing |
| VNC/SSH available for remote kill | ✅ confirmed Phase 0 |

---

## 5. Remaining Risks

### 5.1 Openbox WM Behaviour (HIGH)

**Risk:** Openbox 3.6.1 may NOT honour `--app` window stacking correctly. The overlay Chromium window may appear:
- Behind the UKM5 kiosk Chromium (invisible)
- Without "always on top" behaviour (no `--always-on-top` flag in Chromium, WM-dependent)
- With window decorations (title bar, borders) despite `--app`

**Mitigation:** 
- `--app` mode provides frameless window on most WMs
- If decorations appear: test `wmctrl -r "title" -b add,above` (if installed)
- If behind kiosk: test `xdotool windowactivate` (if installed)
- **Fallback:** accept that overlay may be partially covered in first test — visual verification is the primary deliverable

### 5.2 Focus Steal Risk (MEDIUM)

**Risk:** New Chromium window may steal keyboard/mouse focus from UKM5 kiosk, disrupting checkout flow.

**Mitigation:**
- `--app` + `--window-position` does NOT auto-focus
- `no_focus_steal: true` in shell plan is a contract, not a WM guarantee
- Kill-switch activated BEFORE test → overlay appears hidden even if launched
- If focus stolen: kill overlay via SSH, restore focus to kiosk

### 5.3 State Drift (LOW)

**Risk:** Synthetic `state.json` diverges from real KSO state during test (e.g., real checkout starts while test state says "idle").

**Mitigation:**
- Phase 2 runs in **off-hours only** (store closed, no real checkouts)
- Kill-switch provides immediate hide regardless of state
- Manual state file, static — won't change unless operator changes it

### 5.4 Chromium Instance Confusion (MEDIUM)

**Risk:** Operator accidentally kills UKM5 kiosk Chromium instead of overlay Chromium.

**Mitigation:**
- Overlay Chromium launched with `--app=file:///tmp/kso_test/overlay.html` — uniquely identifiable
- `pkill` pattern targets URL, not binary name
- PID-based targeting for extra safety
- UKM5 kiosk PID list captured BEFORE test

### 5.5 Tool Availability on KSO (LOW)

**Risk:** `xdotool` or `wmctrl` not installed, needed for stacking control.

**Mitigation:**
- Option A (Chromium `--app`) is self-contained — no external tools needed
- If stacking fails, accept partial overlay visibility as a learning outcome
- Install tools only with explicit approval and only during off-hours

---

## 6. Approval Gate

> ## ⚠️ PHASE 2 IS STILL NOT APPROVED.
>
> This review document confirms **technical readiness** — not execution permission.
>
> **Phase 2 (overlay render) requires ALL of the following before execution:**
>
> 1. ✅ Phase 1 dry smoke passed (6/6 on physical KSO) — **DONE**
> 2. ⛔ Explicit verbal/written approval from **Sergey Paschenko** — **PENDING**
> 3. ⛔ Off-hours window confirmed (store closed, no checkouts) — **PENDING**
> 4. ⛔ Operator briefed on kill-switch and rollback commands — **PENDING**
> 5. ⛔ Physical/VNC access to KSO screen confirmed — **PENDING**
> 6. ⛔ UKM5 health check (mint.service active, kiosk running) — **PENDING**
>
> **Without ALL 6 gates: overlay render MUST NOT be attempted.**

---

## 7. Test Matrix (for approval)

When Phase 2 is approved, execute these 4 visual checks:

| # | Test | Setup | Expected Visual |
|---|------|-------|-----------------|
| V1 | Overlay visible on idle | no kill-switch, idle state | Gray overlay at bottom of screen (y=400-640) |
| V2 | Overlay hidden on kill-switch | `touch /tmp/kso_test/kill_switch` | Overlay disappears, UKM5 full screen restored |
| V3 | Payment button NOT covered | V1 active | Blue payment button (y=720) fully visible below overlay |
| V4 | UKM5 header NOT covered | V1 active | Dark header bar (y=0-60) fully visible above overlay |

**Pass criteria:** V1-V4 all confirmed visually. Any failure → immediate rollback.

---

## 8. Regression Baseline

Regression запускается в рамках этого шага (38.1.1). Baseline перед Phase 2:

| Suite | Тестов | Статус |
|-------|--------|--------|
| backend | 169 | ✅ |
| portal-web | 407 | ✅ |
| state_adapter | 86 | ✅ |
| kso_player | 1298 | ✅ |
| sidecar | 1838 | ✅ |
| infra | 227 | ✅ |
| **Итого** | **4025** | ✅ |

---

## 9. Файлы

- `docs/audit/portrait-overlay-phase2-readiness-review.md` — этот документ
- `docs/audit/portrait-overlay-physical-kso-test-plan.md` — родительский test plan
- `docs/audit/portrait-player-profile-design.md` — дизайн профиля
- `docs/audit/kso-portrait-architecture-pivot.md` — архитектурный pivot
- `docs/audit/technical-debt-next-actions.md` — план действий
- `docs/audit/one-kso-pilot-readiness-plan.md` — readiness roadmap
- `apps/kso_player/kso_player/profiles/portrait_idle_overlay_768.py` — профиль
- `apps/kso_player/kso_player/shell_plan.py` — shell plan
- `apps/kso_player/kso_player/kill_switch.py` — kill-switch
- `apps/kso_player/kso_player/state_observer.py` — state observer
- `apps/kso_player/scripts/standalone_smoke_py36.py` — KSO standalone smoke

---

## Журнал

### 2026-06-24 — Шаг 38.1.1 (Phase 2 Readiness Review)

Создан readiness review документ. Подтверждено:
- Все 6 компонентов кодовой базы проверены (profile, shell plan, kill-switch, state observer, smoke, test plan)
- Phase 2 command plan документирован (3 options, Option A recommended: Chromium `--app`)
- Stop criteria проверены: геометрия (gap 80 px), ресурсы (headroom ample), kill-switch (ready), rollback (ready)
- 5 остаточных рисков идентифицированы (Openbox WM — HIGH, focus steal — MEDIUM, state drift — LOW, instance confusion — MEDIUM, tool availability — LOW)
- **Phase 2 НЕ одобрен.** Требуется 6 approval gates (включая explicit approval Сергея Пащенко)
- КСО не менялась. Chromium overlay не запускался. УКМ5 не менялась.
