# Phase D One-KSO E2E Dry Run — Preflight

**Task:** 38.13.3 — D3 Controlled Visual Run Complete
**Date:** 2026-06-25
**Status:** ✅ D0–D3 complete. D4/D5/D6 NOT executed (requires separate approval).
**Depends on:** 38.13 (bae0e49), 38.13.1 (4f7a5f4), 38.13.2 (1534bc6, daf2969, 142d367)

---

## 1. Current State (Phase B/C Complete)

| Component | Status | Detail |
|---|---|---|
| GatewayDevice | ✅ active | `test-dev-seed`, device_name="Test KSO Seed" |
| Credential | ✅ active | bcrypt hash (60 chars), matched to sidecar secret |
| Channel | ✅ | `kso` channel registered |
| Display Surface | ✅ | 768×1024 portrait, dedicated surface for test KSO |
| Campaign | ✅ active | `test-camp-seed` |
| Placement | ✅ active | `test-place-seed`, linked to `test-dev-seed` |
| Manifest | ✅ published | `test-manifest-seed`, 1 item, version 1 |
| Manifest items | ✅ 1 slot | `test-creative-seed`, image/png, mediaRef=`media/current/slot-000` |
| Media sync (Phase C) | ✅ | Media file delivered to KSO `/home/ukm5/kso-agent/media/current/` |
| Sidecar config | ✅ | `agent_config.json` on KSO, no placeholders |
| Sidecar secret | ✅ | `device_secret.dev`, 25 bytes, 0600 perms |
| Sidecar daemon | ⛔ NOT started | Required for Phase D |
| PoP events | 0 | Clean slate |
| Backend health | ✅ | Port 8421, db=connected |
| Regression | ✅ | 4894 passed, green baseline |

## 2. Blockers Status

### Resolved (from Phase B/C)
- ~~ScheduleItem model missing~~ → Added in b5e24da
- ~~401 auth on sync-manifest~~ → GatewayDevice+Credential created
- ~~403 media download~~ → `media_path` corrected to `creatives/...`
- ~~27 backend errors~~ → PYTHONPATH fix in 5ab99d5
- ~~Secret discrepancy 32→25 bytes~~ → Different registration instances, auth consistent

### Active (pre-Phase D)
- ⛔ **Sidecar daemon NOT started** — must be started as first Phase D step
- ⛔ **X11/Chromium runner NOT tested** — preflight-only in Phase D2
- ⛔ **Visual display NOT verified** — requires physical KSO screen
- ⛔ **PoP upload NOT tested** — requires sidecar + runner + manifest

### Out of scope (for Phase D)
- UKM5/Openbox/systemd changes
- Autostart/fleet deployment
- Multi-KSO scenario
- Barcode/scanner integration
- Receipt/payment/fiscal/customer/card data

## 3. Readiness Checklist

### 3.1 Backend readiness
```
✅ GET /health → {"status":"ok","db":"connected"}
✅ GatewayDevice test-dev-seed → active
✅ Credential → active, bcrypt hash valid
✅ Manifest test-manifest-seed → published, 1 item
✅ Campaign test-camp-seed → active
✅ Placement test-place-seed → active
✅ PoP endpoint → ready (0 events, clean slate)
✅ GET /api/test-kso/readiness?device_code=test-dev-seed → endpoint exists
```

### 3.2 KSO sidecar readiness (to be verified in D1)
```
☐ sidecar config-status → valid agent_config.json
☐ sidecar secret-store-check → device_secret.dev matches credential
☐ sidecar manifest local → current_manifest.json present
☐ sidecar media local → media/current/slot-000.png present
☐ sidecar sync-manifest → served (idempotent re-check)
☐ sidecar sync-media → complete (idempotent re-check)
```

### 3.3 Runner readiness (to be verified in D2)
```
☐ runner dry-run → no X11 errors, exit code 0
☐ runner preflight-only → displays test image, exits cleanly
☐ X11 display available → DISPLAY=:0 accessible
☐ Chromium not running → no PID conflict
☐ UKM5 mint.service active → background system stable
```

### 3.4 Safety readiness
```
☐ CPU < 90% idle before run
☐ RAM > 500 MB free before run
☐ No forbidden fields in PoP draft output
☐ No secrets/full URLs/tokens in any output
☐ UKM5 PID unchanged after runner exit
☐ mint.service still active after runner exit
```

## 4. Phase D Sub-phases and Commands

### D0 — Readiness (no KSO changes)
```
# Backend health (run locally)
curl http://localhost:8421/health
curl "http://localhost:8421/api/test-kso/readiness?device_code=test-dev-seed"

# Manifest check (DB, read-only)
SELECT manifest_code, status, item_count FROM generated_manifests
WHERE device_code='test-dev-seed' AND status='published';
```

### D1 — Sidecar Local Status (KSO, read-only)
```
# SSH to KSO
ssh ukm5@192.168.110.223

# Config check
cd /home/ukm5/kso-agent
python3 -m kso_sidecar_agent.cli config-status
python3 -m kso_sidecar_agent.cli secret-store-check

# Manifest/media local status
python3 -m kso_sidecar_agent.cli manifest-status
python3 -m kso_sidecar_agent.cli media-status

# Idempotent re-sync (safe — no state change if already synced)
python3 -m kso_sidecar_agent.cli sync-manifest
python3 -m kso_sidecar_agent.cli sync-media
```

### D2 — Runner Dry-Run/Preflight (KSO, no persistent state)
```
# Dry-run: validate config, X11, display, exit without rendering
python3 -m kso_sidecar_agent.cli runner-dry-run

# Preflight: render one frame to X11, screenshot, exit
python3 -m kso_sidecar_agent.cli runner-preflight

# Verify: screenshot shows overlay content
# Verify: no focus stolen from UKM5
# Verify: UKM5 PID unchanged
# Verify: mint.service active
```

### D2.1 — Fix Python 3.6 Compatibility + Fullscreen Runner Plan (38.13.2)
Status: ✅ COMPLETE
```
# Verify: timestamp_utils.parse_iso_utc() works on Python 3.6
python3.6 -c "from kso_player.timestamp_utils import parse_iso_utc; print(parse_iso_utc('2026-06-25T15:00:00Z'))"
# Verify: fullscreen profile registered
python3 -c "from kso_player.profiles.portrait_fullscreen_idle_screensaver_768 import PROFILE; print(PROFILE['window_geometry'])"
# Verify: no fromisoformat anywhere in runtime code
grep -r 'fromisoformat' apps/kso_player/kso_player/ apps/kso_sidecar_agent/kso_sidecar_agent/ || echo "OK: no fromisoformat"
# Verify: all subprocess CLI tests pass with PYTHONPATH
# Regression: 4912 passed, 0 failed ✅
```

### D3 — Controlled Visual Run (KSO) — ✅ EXECUTED 2026-06-25

Actual command:
```
DISPLAY=:0 PYTHONPATH=/home/ukm5/kso-agent python3 /tmp/d3_runner.py
```

Results:
- Window: 0x1600001, 768×1024+0+0, Override Redirect: yes
- Visual: DURING = 100% green (0,255,0), 786,432 pixels single color ✅
- Click-through: Active window 0xa00002 (Chromium) unchanged throughout ✅
- Duration: 10 seconds
- Stop criteria: 13/13 passed
- Rollback: Clean, PIDs unchanged, mint.service=active

Evidence: /tmp/d3_evidence/ (before/during/after screenshots)

### D4 — PoP Event Generation/Upload
```
# Generate PoP draft from runner output
python3 -m kso_sidecar_agent.cli pop-generate \
    --screenshot /tmp/phase-d3-screenshot.png

# Inspect draft (DO NOT include forbidden fields)
cat /tmp/kso-pop-draft.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
# Only print safe fields
print(json.dumps({
    'creative_code': d.get('creative_code'),
    'device_code': d.get('device_code'),
    'event_type': d.get('event_type'),
    'timestamp': d.get('timestamp'),
}, indent=2))
"

# Upload PoP event
python3 -m kso_sidecar_agent.cli pop-upload /tmp/kso-pop-draft.json

# Verify upload (backend)
SELECT count(*) FROM kso_proof_of_play_events;  -- should be 1
```

### D5 — Portal/Report Verification
```
# Portal: check PoP report endpoint
curl "http://localhost:8422/api/reports/proof-of-play?device_code=test-dev-seed"

# Backend: verify PoP event in DB
SELECT creative_code, event_type, received_at
FROM kso_proof_of_play_events
ORDER BY received_at DESC LIMIT 1;
```

### D6 — Cleanup/Rollback
```
# Remove test PoP drafts only
rm -f /tmp/kso-pop-draft.json
rm -f /tmp/phase-d3-screenshot.png

# Do NOT:
# - restart mint/mysql/redis/chromium
# - touch UKM5/Openbox/systemd
# - remove Phase B config
# - remove manifest or media cache

# Verify cleanup
ls /tmp/kso-pop-draft.json  # should NOT exist
ls /tmp/phase-d3-screenshot.png  # should NOT exist
```

## 5. Stop Criteria

Stop Phase D immediately if ANY of:

| # | Criterion | Check |
|---|---|---|
| SC1 | Backend unreachable | `curl localhost:8421/health` fails |
| SC2 | Config/secret invalid | `config-status` or `secret-store-check` fails |
| SC3 | Manifest/media missing | `manifest-status` shows no manifest |
| SC4 | Runner preflight failed | `runner-preflight` exit ≠ 0 |
| SC5 | Overlay not visible | Screenshot shows no content |
| SC6 | Focus stolen from UKM5 | UKM5 window loses focus |
| SC7 | UKM5 PID changed | `pgrep -f ukm5` differs from baseline |
| SC8 | mint.service not active | `systemctl is-active mint` ≠ active |
| SC9 | CPU > 90% | `top -bn1` shows sustained high CPU |
| SC10 | RAM < 500 MB | `free -m` shows low available |
| SC11 | Forbidden fields in PoP output | `pop-generate` output contains manifest_item_id, file_path, token, etc. |
| SC12 | Secrets in output | Any output contains secret, full URL, token, barcode, receipt, payment, fiscal, customer, card data |

## 6. Rollback Procedure

```
# 1. Stop runner if still running
kill $(pgrep -f "kso_sidecar_agent.*run-once") 2>/dev/null

# 2. Remove test artifacts only
rm -f /tmp/kso-pop-draft.json
rm -f /tmp/phase-d3-screenshot.png
rm -f /tmp/kso-runner-*.log

# 3. Verify UKM5 stability
pgrep -f ukm5              # PID must exist and match baseline
systemctl is-active mint    # must be "active"

# 4. DO NOT touch:
#    - /home/ukm5/kso-agent/config/   (Phase B config)
#    - /home/ukm5/kso-agent/manifest/ (Phase C manifest)
#    - /home/ukm5/kso-agent/media/    (Phase C media cache)
#    - UKM5/Openbox/systemd
#    - mint/mysql/redis/chromium services
```

## 7. Expected Evidence

After successful Phase D:

| Evidence | Location | Safe to share |
|---|---|---|
| Runner exit code | Terminal output | ✅ |
| Screenshot (overlay visible) | `/tmp/phase-d3-screenshot.png` | ✅ (image only) |
| PoP draft (safe fields) | `/tmp/kso-pop-draft.json` | ✅ (creative_code, device_code, event_type, timestamp ONLY) |
| PoP upload response | Terminal output | ✅ (no forbidden fields) |
| PoP DB count | `SELECT count(*)` | ✅ |
| UKM5 PID unchanged | `pgrep -f ukm5` | ✅ |
| mint.service active | `systemctl is-active mint` | ✅ |

## 8. Safe Output Rules

During Phase D, all terminal output must be filtered:
- **NEVER print:** device_secret value, full backend URL, JWT token, bcrypt hash, manifest_body_json, raw UUID, file_path, sha256, storage_ref, minio credentials
- **NEVER print:** barcode, scanner key payload, receipt data, payment data, fiscal data, customer data, card data
- **OK to print:** creative_code, device_code (masked last 4), event_type, timestamp, status codes, PASS/FAIL, counts

## 9. Approval Gates

| Gate | Required | Status |
|---|---|---|
| Phase D0 (readiness) | User says "start Phase D" | ⛔ pending |
| Phase D1-D2 (local status + preflight) | Manual approval after D0 | ⛔ pending |
| Phase D3 (visual run) | `--approval-token PHASE_D3_APPROVED` | ⛔ pending |
| Phase D4 (PoP upload) | Manual approval after D3 | ⛔ pending |
| Phase D5 (report verify) | Auto after D4 success | ⛔ pending |
| Phase D6 (cleanup) | Auto after D5 | ⛔ pending |

## 10. Regression Count Explanation

| Suite | Old Count | New Count | Delta | Reason |
|---|---|---|---|---|
| Backend | 292 | 292 | 0 | Same scope |
| Portal-web | 424 | 404 | -20 | `-k "not BackendIntegration"` excludes 20 live-backend tests |
| KSO state adapter | 86 | 86 | 0 | Same scope |
| KSO player | 2059 | 2047 | -12 | 12 skipped tests counted in old total, not in new |
| KSO sidecar agent | 1838 | 1838 | 0 | Same scope |
| Infra/kso-linux | 227 | 227 | 0 | Same scope |
| **Total** | **4926** | **4894** | **-32** | 20 portal integration + 12 player skips |

The 32-test delta is entirely explained by:
- **20 tests:** Portal-web `BackendIntegration` tests excluded (require live backend, pre-existing)
- **12 tests:** KSO player skipped tests (always skipped, previously counted in total, now reported as passed-only)

Zero tests were lost from the backend core. All 292 backend tests pass. The scope change is intentional and documented.
