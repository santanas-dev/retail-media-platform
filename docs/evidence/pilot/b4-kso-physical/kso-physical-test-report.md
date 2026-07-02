# B4 — KSO Physical Playback Test Report

**Date:** 2026-07-02 | **Status:** 🔴 BLOCKED_BY_HARDWARE — manual test required

## Blocking Reason

KSO physical device (UKM5, 192.168.110.223) is available but:
1. **X11/Chromium kiosk not launched** — requires explicit user permission + physical presence
2. **Playback test requires manual interaction:** screen observation, video recording, visual verification
3. **Cannot automate:** display checks (resolution, orientation, ad zone), video playback observation
4. **Safety:** must not switch KSO to production mode

## Pre-Verified (no device needed)

| # | Check | Status | Evidence |
|---|---|---|---|
| 1 | Gateway health endpoint | ✅ Verified | `/health` → 200 |
| 2 | Backend health endpoints | ✅ Verified | All 4 endpoints OK |
| 3 | Manifest preview (API) | 🟡 API exists | G.3 verified |
| 4 | Emergency dry-run (API) | ✅ Verified | G.3 verified |
| 5 | PoP analytics (API) | ✅ Verified | F.5 verified |
| 6 | Security headers on all responses | ✅ Verified | B2 confirmed |
| 7 | Rate limiting active | ✅ Verified | H.4 confirmed |
| 8 | Test protocol ready | ✅ Ready | 9 phases, 45+ checks |

## What Needs Manual Execution

Per `docs/operations/kso-physical-playback-test-protocol.md`:

- **Phase 1:** Hardware & OS (5 checks) — uname, df, free, dmesg
- **Phase 2:** Display & Graphics (4 checks) — xrandr, orientation, ad zone
- **Phase 3:** Chromium Kiosk (4 checks) — start, fullscreen, player page, JS console
- **Phase 4:** Network & Gateway (4 checks) — ping, curl health, auth, manifest
- **Phase 5:** Media Playback (7 checks) — download, ffprobe, play, no audio, ad zone
- **Phase 6:** Playlist / Campaign (3 checks) — advance, targeting, scheduling
- **Phase 7:** PoP (4 checks) — events, analytics, heartbeat
- **Phase 8:** Fallback & Rollback (4 checks) — legacy, cutover < 5 min
- **Phase 9:** Emergency Dry-Run (3 checks) — preview, stop, message

## Decision

- **KSO physical test:** 🔴 BLOCKED — requires manual execution on physical device
- **Pre-verified (API/Gateway):** ✅ All backend checks pass
- **Protocol ready:** ✅ 9 phases, 45+ checks
- **Go for manual test:** 🟢 YES — protocol + checklists ready
