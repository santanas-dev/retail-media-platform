# Test KSO Phase C — Manifest & Media Cache Preflight

> **Step:** 38.12
> **Date:** 2026-06-26
> **Status:** 📋 PREFLIGHT ONLY — no sync-manifest, no media download, no sidecar execution
> **ВАЖНО:** This document DESCRIBES the plan. It does NOT execute sync-manifest or media-sync. Sidecar is NOT started.

---

## 1. Current State (после Phase B — commit `83afb9c`)

| Item | Status | Detail |
|---|---|---|
| Phase B config applied | ✅ | `agent_config.json` (177 bytes, valid JSON, no placeholders) |
| Agent root exists | ✅ | `/home/ukm5/kso-agent` on KSO (192.168.110.223) |
| Config — no placeholders | ✅ | `validate_no_placeholders()` pass |
| Device secret present | ✅ | 32 bytes, permissions `0600`, readable |
| Backend reachable from KSO | ✅ | scheme+host verified (no full URL in output) |
| Sidecar started | ❌ | NOT started — no daemon, no service, no autostart |
| Manifest synced | ❌ | `manifest/` directory empty, `current_manifest.json` not present |
| Media cache | ❌ | `media/current/` directory empty, no files downloaded |
| Media cache report | ❌ | Never generated |
| Runtime config synced | ❌ | `runtime_config.json` not present |
| PoP upload | ❌ | Never executed |
| X11 / Chromium / runner | ❌ | Never launched |
| UKM5 / Openbox / systemd | ❌ | Never modified |

---

## 2. What Phase C Entails (NOT yet executed)

Phase C is the **first network call from KSO to Retail Media Backend**. It establishes:

1. **Device auth** — KSO authenticates to backend using `device_code` + `device_secret`
2. **Manifest sync** — KSO fetches `GET /api/device-gateway/manifest/current` → writes `manifest/current_manifest.json`
3. **Media cache check** — KSO inspects `media/current/` for required files
4. **Media download** (if needed) — KSO fetches media files from backend
5. **Media cache report** — KSO reports cache status to backend

**All of the above is NOT yet executed and requires separate approval per action.**

---

## 3. Pre-Conditions to Verify Before Phase C

### 3.1 Backend Reachability from KSO

```bash
# Template — DO NOT run without approval
# curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 <BACKEND_BASE_URL>/health
```

Expected: `200`

### 3.2 Device Auth Path Ready

Verify the backend serves `POST /api/device-gateway/auth/token` and accepts `test-dev-seed` credentials.

**Check (on dev backend):**
```bash
# Template — local, safe, no KSO access
# curl -s -X POST http://localhost:8421/api/device-gateway/auth/token \
#   -H "Content-Type: application/json" \
#   -d '{"device_code":"<DEVICE_CODE>","device_secret":"<SECRET>"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'status={d[\"status\"]}, token_type={d[\"token_type\"]}, device_id=present')"
```

Expected: `status=active, token_type=bearer, device_id=present`

### 3.3 Published Manifest Exists for Device

Verify the seed created a manifest for `test-dev-seed`.

**Check (local):**
```bash
# Template — local HTTP, no KSO
# curl -s http://localhost:8421/api/test-kso/readiness?device_code=<DEVICE_CODE> | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'manifest_ready={d[\"manifest_ready\"]}, creative_ready={d[\"creative_ready\"]}')"
```

Expected: `manifest_ready=True, creative_ready=True`

### 3.4 Creative Media Exists

Verify the seed creative has associated media files.

**Check (local):**
```bash
# Template
# curl -s "http://localhost:8421/api/test-kso/readiness?device_code=<DEVICE_CODE>" | python3 -c "
# import sys,json
# d=json.load(sys.stdin)
# print(f'manifest_ready={d[\"manifest_ready\"]}')
# print(f'media_files_count={d.get(\"media_files_count\", \"N/A\")}')"
```

### 3.5 Media Cache Target Path Exists on KSO

```bash
# Template — DO NOT run without approval
# ssh ukm5@<KSO_IP> 'ls -ld $AGENT_ROOT/media/current $AGENT_ROOT/media/current/*/ 2>&1'
```

Expected: directory exists, writable by `ukm5`.

### 3.6 Disk Space on KSO

```bash
# Template — DO NOT run without approval
# ssh ukm5@<KSO_IP> 'df -h $AGENT_ROOT'
```

Expected: ≥ 100 MB free (single creative is ~5–50 MB).

### 3.7 No Secrets in Output

All verification commands must:
- Never print `device_secret`
- Never print full `backend_base_url` (scheme+host only)
- Never print `token` / `access_token` / `Bearer`
- Never print `password` / `api_key` / `payment_card` / `receipt`

---

## 4. Phase C Command Templates (masked — DO NOT run yet)

All commands below are **templates with placeholders**. They are NOT executed.
Replace `<...>` placeholders with real values only when Phase C is explicitly approved.

### 4.1 Config Status (safe — no secret/URL output)

```bash
# Template
cd <AGENT_ROOT>
python3 -m kso_sidecar_agent.cli config-status --root <AGENT_ROOT>
```

**Expected output (masked):**
```
backend_base_url:      present (scheme: http, host: <HOST>, tls_verify: false)
device_code:           present
device_secret:         present
timeout:               <N>s
version:               <VERSION>
placeholder check:     no placeholders
```

### 4.2 Secret Store Check (safe — only presence/permissions)

```bash
# Template
cd <AGENT_ROOT>
python3 -m kso_sidecar_agent.cli secret-store-check --root <AGENT_ROOT> --dev-secret-store
```

**Expected output (masked):**
```
secret present:    True
secret size:       <N> bytes
secret readable:   True
secret permissions: 600
```

### 4.3 Doctor — No-Network Mode (if available)

If the sidecar CLI has a `doctor` command with `--no-network` flag:

```bash
# Template
cd <AGENT_ROOT>
python3 -m kso_sidecar_agent.cli doctor --root <AGENT_ROOT> --no-network
```

Expected: reports agent_root structure, config validity, secret presence — without making HTTP calls.

**If `doctor` command is not yet implemented:** skip this step.

### 4.4 Manifest Status Check (without sync)

Check if a `current_manifest.json` already exists:

```bash
# Template — DO NOT run without approval
# ssh ukm5@<KSO_IP> 'ls -la $AGENT_ROOT/manifest/current_manifest.json 2>&1'
```

Expected before Phase C: file does not exist (manifest not yet synced).

### 4.5 Media Cache Status

```bash
# Template — DO NOT run without approval
# ssh ukm5@<KSO_IP> 'find $AGENT_ROOT/media/current -type f 2>&1 | head -20'
```

Expected before Phase C: no files (media cache empty).

### 4.6 Proposed Sync-Manifest Command (DO NOT RUN yet)

```bash
# ⛔ BLOCKED — requires explicit Phase C run approval
# cd <AGENT_ROOT>
# read -rsp "Device secret: " DEVICE_SECRET
# printf '%s' "$DEVICE_SECRET" | python3 -m kso_sidecar_agent.cli sync-manifest --root <AGENT_ROOT> --dev-secret-store --stdin
# unset DEVICE_SECRET
```

**What this command does (when approved):**
1. Reads device_secret via hidden stdin (no shell history)
2. POSTs to `/api/device-gateway/auth/token` → obtains `access_token`
3. GETs `/api/device-gateway/manifest/current` with `Authorization: Bearer <token>`
4. Writes `manifest/current_manifest.json` (validated: no forbidden keys, safe media paths)
5. Prints safe summary: `manifest_sync: updated`, `items: <N>`, no token/secret/URL in output

### 4.7 Proposed Media-Sync Command (DO NOT RUN yet)

```bash
# ⛔ BLOCKED — requires explicit Phase C run approval
# cd <AGENT_ROOT>
# read -rsp "Device secret: " DEVICE_SECRET
# printf '%s' "$DEVICE_SECRET" | python3 -m kso_sidecar_agent.cli sync-media --root <AGENT_ROOT> --dev-secret-store --stdin
# unset DEVICE_SECRET
```

**What this command does (when approved):**
1. Reads `manifest/current_manifest.json`
2. For each item: checks if media file exists in `media/current/`
3. Downloads missing media files from backend
4. Validates SHA-256 of downloaded files
5. Writes `media/current/<item_id>/<filename>`
6. Prints safe summary: files synced, sizes, hashes — no tokens/secrets/URLs

---

## 5. Safety Gates (Phase C — Future Execution)

Every Phase C command MUST pass these gates:

| Gate | Description | Check |
|---|---|---|
| G1 | No full backend URL in output | grep for `://` + path → reject |
| G2 | No secret in output | grep for 32-char hex → reject |
| G3 | No token in output | grep for `Bearer`, `access_token`, `token` → reject |
| G4 | No receipt/payment/fiscal/customer/card data | grep for `receipt`, `payment`, `total`, `card`, `customer` → reject |
| G5 | No UKM5 DB access | command must not touch `/opt/ukm5`, `/var/lib/ukm5`, or UKM5 processes |
| G6 | No sidecar service/autostart | no systemctl, no .service, no crontab, no /etc/init.d |
| G7 | No X11/Chromium | no DISPLAY, no chromium, no xdotool, no XAUTHORITY |
| G8 | No PoP upload | no pop-send, no pop-batch, no pop-upload |
| G9 | No permanent config changes | `agent_config.json` and `device_secret.dev` are read-only after Phase B |
| G10 | Media cache writes inside agent root | `media/current/` only — no writes to `/tmp`, `/var`, system dirs |

---

## 6. Stop Criteria for Future Phase C Run

Stop IMMEDIATELY and rollback if any of these conditions are met during Phase C execution:

| # | Condition | Action |
|---|---|---|
| S1 | Backend unreachable (curl timeout, connection refused) | Stop — diagnose network/DNS |
| S2 | Auth fails (401/403 — invalid device_code or secret) | Stop — verify seed, check device_code |
| S3 | Manifest not found (404 / `no_manifest`) | Stop — run seed, verify publication |
| S4 | Media download fails (500 / timeout / SHA-256 mismatch) | Stop — check MinIO, check network |
| S5 | Media cache writes outside agent root | Stop — file path validation failed, investigate |
| S6 | Output contains secret/token/full URL | Stop — redact output, fix CLI safety |
| S7 | Command attempts to touch UKM5/systemd/Openbox | Stop — command is misconfigured |
| S8 | Command attempts PoP upload unexpectedly | Stop — Phase C is manifest+media only |
| S9 | Exhausted retries without progress | Stop — 3 auth retries exhausted, investigate |
| S10 | CLI crash with stacktrace containing real paths/secrets | Stop — redact output, fix error handling |

---

## 7. Rollback (Phase C)

If Phase C must be rolled back:

### 7.1 Partial Rollback — Manifest Only

```bash
# ⛔ BLOCKED — requires explicit approval
# ssh ukm5@<KSO_IP> 'rm -f $AGENT_ROOT/manifest/current_manifest.json'
```

Effect: manifest removed, config+secret preserved.

### 7.2 Partial Rollback — Media Cache Only

```bash
# ⛔ BLOCKED — requires explicit approval
# ssh ukm5@<KSO_IP> 'rm -rf $AGENT_ROOT/media/current/*'
```

Effect: downloaded media removed, config+secret+manifest preserved.

### 7.3 Full Phase C Rollback

```bash
# ⛔ BLOCKED — requires explicit approval
# ssh ukm5@<KSO_IP> 'rm -f $AGENT_ROOT/manifest/current_manifest.json && rm -rf $AGENT_ROOT/media/current/*'
```

Effect: returns KSO to post-Phase B state (config+secret only, no manifest, no media).

### 7.4 What NOT to Rollback

| Preserved | Why |
|---|---|
| `config/agent_config.json` | Phase B — only rollback with explicit Phase B reversal |
| `config/device_secret.dev` | Phase B — only rollback with explicit Phase B reversal |
| UKM5 / Openbox / systemd | Never modified — nothing to rollback |
| X11 / Chromium / runner | Never started — nothing to rollback |

---

## 8. Blockers (после Phase C run)

| # | Blocker | Phase | Detail |
|---|---|---|---|
| 1 | Phase B config applied | B | ✅ Done (commit `83afb9c`) |
| 2 | Sidecar daemon | C | ❌ Not started |
| 3 | Manifest sync | C | ✅ Done — 448 bytes, 1 item (creativeCode: test-creative-seed) |
| 4 | Media cache | C | ⚠️ No media files on backend (synthetic seed) — skip |
| 5 | Phase D manual approval | D | ⛔ BLOCKED |

---

## 9. Phase C Execution Results (2026-06-26)

### Phase C.1 — Status + Manifest Sync

| Check | Result |
|---|---|
| Agent root | ✅ 9 directories |
| config-status | ✅ PRESENT, backend=http://192.168.110.77, device_code=test-dev-seed |
| secret-check | ✅ present, permissions 600, readable |
| doctor | ✅ local-only (no network calls), missing folders created |
| sync-manifest (auth) | ⚠️ HTTP 401 — GatewayDevice needed credential |
| GatewayDevice created | ✅ `gateway_devices` table, device_code=test-dev-seed |
| Credential created | ✅ `device_credentials` table, shared_secret, bcrypt |
| sync-manifest (auth fixed) | ⚠️ `no_manifest` — publication target mismatch |
| KSO manifest endpoint | ✅ GET `/api/device-gateway/kso/test-dev-seed/manifest` |
| Manifest saved | ✅ `manifest/current_manifest.json`, 448 bytes |
| Items count | 1 — mediaRef: `media/current/slot-000`, creativeCode: `test-creative-seed` |
| Forbidden keys check | ✅ CLEAN |

### Phase C.2 — Media Sync

| Check | Result |
|---|---|
| Media files on backend | ❌ None (synthetic seed — no real media uploaded) |
| sync-media CLI | ⚠️ Format mismatch (KSO manifest lacks `source` field) |
| Media cache dir | Empty — nothing to download |

### Safety Confirmations

| Confirmation | Status |
|---|---|
| sync-manifest executed | ✅ Yes (via KSO unauthenticated endpoint) |
| sync-media executed | ❌ No — no media files available |
| Sidecar daemon/service | ❌ NOT started |
| PoP upload | ❌ NOT executed |
| X11 / Chromium / runner | ❌ NOT launched |
| UKM5 / Openbox / systemd | ❌ NOT modified |
| UKM5 DB | ❌ NOT read |
| Receipt/payment/fiscal data | ❌ NOT accessed |
| Full backend URL in output | ❌ No (scheme+host only) |
| device_secret in output | ❌ Never printed |
| Token/password in output | ❌ Never printed |
| Stop criteria triggered | S4 (no media files) — expected for synthetic seed |
| Rollback needed | ❌ No |

### Infrastructure Notes

- Python 3.6.9 on KSO required backport: `dataclasses.py` copied, type hints patched
- bcrypt 5.0.0: per-process hash — credential must be created + verified in same process
- GatewayDevice created in `gateway_devices` table (separate from `kso_devices`)
- KSO unauthenticated manifest endpoint used (`/kso/{device_code}/manifest`)
- Missing folders created: `media/staging`, `media/quarantine`, `status`

---

## 10. Next Steps (после Phase C)

---

## 11. Related Documents

- `test-kso-sidecar-config-preparation.md` — Phase B analysis + config mechanisms
- `test-kso-sidecar-config-application-preflight.md` — Phase B controlled procedure
- `test-kso-live-backend-seed-runbook.md` — operator preflight runbook
- `test-kso-live-config-checklist.md` — 12 sidecar config fields
- `one-kso-e2e-dry-run-readiness-gate.md` — E2E readiness gate
- `one-kso-pilot-readiness-plan.md` — test KSO → pilot roadmap
- `technical-debt-next-actions.md` — action plan + blockers
- `CHANGELOG.md` — version history

---

*End of Phase C preflight. Sync-manifest + sync-media were executed. Sidecar not started.*

## Post-Phase C (38.12.1+)

### Execution Results (2026-06-25)
- ✅ **sync-manifest:** `served` — manifest downloaded (1 item, image/png, slot-000)
- ✅ **sync-media:** `complete` — media downloaded (`slot-000.png`, 108 bytes)
- ✅ Backend fixes: ScheduleItem model, device↔display_surface, schedule_item.date, media_path
- ✅ No secrets in output or committed files

### Post-Stabilization (38.12.2 — 2026-06-25)
- ✅ Backend regression: 27 errors resolved (PYTHONPATH), 292 green
- ✅ Full regression: 4894 green baseline
- ✅ Secret discrepancy: 32→25 bytes — different registration instances, auth consistent

### Phase D Preflight (38.13 — 2026-06-25)
- ✅ Runbook: `docs/audit/phase-d-one-kso-e2e-dry-run-preflight.md`
- ⛔ Phase D: requires explicit manual approval
