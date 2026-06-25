# X11 Screensaver Runner Design

**Updated:** 2026-06-25 (D3 — physical visual run executed ✅)

## Profiles

| Profile | Geometry | Type | D3 Result |
|---|---|---|---|
| `portrait_idle_overlay_768` | 768×240+0+400 | overlay | ❌ (Phase D2) |
| `portrait_fullscreen_idle_screensaver_768` | 768×1024+0+0 | fullscreen kiosk | ✅ (D3 physical run) |

## D3 Physical Run Results (2026-06-25)

- **KSO:** 192.168.110.223, DISPLAY=:0, Python 3.6.9
- **Window:** 0x1600001, 768×1024+0+0, Override Redirect: yes, IsViewable
- **Visual:** DURING screenshot = 100% green (0,255,0), 786,432 pixels single color
- **Click-through:** Active window 0xa00002 (КСО - Chromium) unchanged before/during/after
- **Stop criteria:** 13/13 passed
- **Rollback:** Window destroyed, PIDs unchanged, mint.service=active
- **D4/D5/D6:** NOT executed

## Fullscreen Profile (portrait_fullscreen_idle_screensaver_768)

- **Root:** 768×1024 portrait
- **Window:** 768×1024+0+0 (fullscreen)
- **Type:** kiosk
- **fullscreen:** True
- **idle_only:** True
- **kill_switch_required:** True
- **no_ukm5_db:** True
- **show_on_states:** `['idle']`
- **hide_on_states:** `['busy', 'cart', 'error', 'offline', 'payment', 'scan', 'stale', 'unknown']`
- **Planned renderer/input mode:** `x11_click_through`

## Python 3.6 Compatibility (D2.1)

KSO runs Python 3.6.9. `datetime.fromisoformat` was added in Python 3.7.

### Files fixed

| File | Old | New |
|---|---|---|
| `runtime_gate.py` | `datetime.fromisoformat(raw)` | `parse_iso_utc(raw)` |
| `screensaver_creative.py` | `datetime.fromisoformat(self.valid_to)` | `parse_iso_utc(self.valid_to)` |
| `state_observer.py` | `datetime.fromisoformat(ts.replace("Z", "+00:00"))` | `parse_iso_utc(updated_at_utc)` |
| `run_cycle.py` | `datetime.fromisoformat(ts.replace("Z", "+00:00"))` ×2 | `parse_iso_utc(ts)` ×2 |
| `simulator.py` | `datetime.fromisoformat(iso)` | `parse_iso_utc(iso)` |

### Replacement: `kso_player.timestamp_utils.parse_iso_utc()`

- Uses `strptime`, NOT `fromisoformat`
- Handles: Z suffix, microseconds, +00:00 offset, no timezone
- Returns naive UTC datetime or None on failure
- Invalid timestamp → None → safe stale/unknown/hidden default

### Tests

13 tests in `apps/kso_player/tests/test_timestamp_utils.py`:
- Z suffix + microseconds
- offset + microseconds
- no timezone
- invalid → None
- None/empty/whitespace/non-string → None
- result is naive datetime
- real KSO format
- no `fromisoformat` in runtime code
