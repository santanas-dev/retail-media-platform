# Device / Sidecar Dashboard Analysis

> **Phase:** 39.4.0 — Analysis First
>
> Date: 2026-06-26
> Baseline: v0.10.0-approval-publication-hardening (commit `30ac341`)
> Regression: 5042 tests green

---

## Executive Summary

Audit device registry, device gateway, sidecar agent status, and portal device/readiness pages. **Key finding:** substantial device infrastructure exists (GatewayDevice, KsoDevice, DeviceHeartbeat, DeviceSession, DeviceCredential, etc.), but it is **not surfaced** in a unified dashboard. Portal `/devices` page shows KSO device registry data only — no heartbeat, auth status, sidecar version, or manifest/media readiness. The `readiness` page is test-kso-only (hardcoded lookup). Backend has rich data but no aggregation endpoint for a pilot operator dashboard.

---

## 1. Current State

### 1.1 Device Models

| Model | Table | Purpose | Key fields |
|---|---|---|---|
| **KsoDevice** | `kso_devices` | Hierarchy registry (store-linked) | `device_code`, `status` (active/inactive/blocked/maintenance/lost), `sidecar_version`, `player_version`, `last_seen_at`, screen geometry |
| **GatewayDevice** | `gateway_devices` | Device gateway identity | `device_code`, `status` (pending/active/disabled), `last_seen_at`, FK to store/channel/display_surface |
| **DeviceCredential** | `device_credentials` | Auth credential (shared secret / cert) | `credential_type`, `status` (active/expired/revoked), `expires_at`, `secret_hash` |
| **DeviceSession** | `device_sessions` | Active JWT session | `access_token_hash`, `expires_at`, `last_used_at`, `client_ip` |
| **DeviceHeartbeat** | `device_heartbeats` | Heartbeat record | `status`, `app_version`, `os_version`, `storage_free_mb`, `cache_items_count`, `current_manifest_hash`, `created_at` |
| **DeviceEvent** | `device_events` | Audit events | `event_type`, `severity`, `message`, `details_json` |
| **DeviceManifestRequest** | `device_manifest_requests` | Manifest request log | `request_status`, `manifest_version_id`, `client_manifest_hash` |
| **DeviceMediaRequest** | `device_media_requests` | Media download log | `request_status`, `media_path`, `expected_sha256`, `response_size_bytes` |

**Assessment:** Very rich model layer. GatewayDevice has relationships to heartbeats, sessions, credentials, manifest_requests, media_requests, pop_events, pop_batches — ready for dashboard aggregation.

### 1.2 Backend Endpoints

#### Device Gateway (production — device-facing)

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/api/device-gateway/auth/token` | POST | Device secret | Auth → JWT |
| `/api/device-gateway/me` | GET | JWT | Device info |
| `/api/device-gateway/heartbeat` | POST | JWT | Heartbeat |
| `/api/device-gateway/manifest/current` | GET | JWT | Current manifest |
| `/api/device-gateway/manifest/{id}` | GET | JWT | Manifest by ID |
| `/api/device-gateway/manifest/kso/{code}` | GET | JWT | KSO manifest |
| `/api/device-gateway/media/{id}` | GET | JWT | Media download |
| `/api/device-gateway/media/kso/{code}/{media_ref}` | GET | JWT | KSO media download |
| `/api/device-gateway/media/cache/report` | POST | JWT | Media cache report |
| `/api/device-gateway/config/current` | GET | JWT | Runtime config |
| `/api/device-gateway/config/manifest/apply` | POST | JWT | Manifest apply |
| `/api/device-gateway/pop/event` | POST | JWT | Single PoP event |
| `/api/device-gateway/pop/batch` | POST | JWT | PoP batch |
| `/api/device-gateway/pop/events` | GET | JWT | List events |
| `/api/device-gateway/pop/batches` | GET | JWT | List batches |

#### Gateway Admin (portal-facing)

| Endpoint | Method | Permission | Purpose |
|---|---|---|---|
| `/api/gateway-devices` | POST | `devices.gateway.manage` | Create device |
| `/api/gateway-devices` | GET | `devices.gateway.read` | List devices |
| `/api/gateway-devices/{id}` | GET | `devices.gateway.read` | Get device |
| `/api/gateway-devices/{id}` | PATCH | `devices.gateway.manage` | Update device |
| `/api/gateway-devices/{id}/credentials` | POST | `devices.gateway.credentials` | Create credential |
| `/api/gateway-devices/{id}/credentials/{cid}/revoke` | POST | `devices.gateway.credentials` | Revoke credential |
| `/api/gateway-devices/{id}/heartbeats` | GET | `devices.gateway.read` | List heartbeats |
| `/api/gateway-devices/{id}/events` | GET | `devices.gateway.read` | List events |
| `/api/gateway-devices/{id}/manifest-requests` | GET | `devices.gateway.read` | Manifest request log |
| `/api/gateway-devices/{id}/media-requests` | GET | `devices.gateway.read` | Media request log |
| `/api/gateway-devices/{id}/pop-events` | GET | `devices.gateway.read` | PoP events |
| `/api/gateway-devices/{id}/pop-batches` | GET | `devices.gateway.read` | PoP batches |

**Assessment:** Admin endpoints cover individual device detail (including heartbeats, events, manifest/media requests, PoP). But there is **NO aggregation endpoint** for a dashboard view — e.g., `GET /api/device-dashboard` returning all devices with their last heartbeat, credential status, manifest status, etc. in one call.

#### KSO Hierarchy

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/hierarchy/kso-devices` | GET | List KSO devices (registry) |
| `/api/hierarchy/kso-devices/{code}` | GET | Get KSO device by code |

**Assessment:** KSO registry lists devices with `sidecar_version`, `last_seen_at`, screen geometry — but `last_seen_at` is only updated when `sync_device_metadata` is explicitly called, NOT from heartbeat. Heartbeat goes to GatewayDevice, not KsoDevice. **Two separate device registries with partial overlap.**

### 1.3 Sidecar Agent Status

The sidecar agent has local status via `agent_status.json` (`agent_status.py`):
- Status: `stopped` | `starting` | `running` | `warning` | `error` | `offline`
- `cached_items`, `invalid_hash_items`
- `errors` list (validated, no secrets)
- `_cycle`: last cycle status, offline_ready flag

Player readiness (`player_readiness.py` — local-only):
- Checks manifest presence and validity
- Checks media cache completeness
- Returns: `ready`, `can_play_local_content`, `manifest_status`, media counts

**Assessment:** Rich local status — but **NOT sent to backend** in heartbeat (heartbeat only sends `status`, `app_version`, `os_version`, `storage_free_mb`, `cache_items_count`, `current_manifest_hash`). Sidecar status (`running`/`warning`/`error`) and errors list are local-only. The heartbeat does include `current_manifest_hash` and `cache_items_count` but these are not aggregated for dashboard view.

### 1.4 Portal Pages

| Page | Source | What it shows | Gaps |
|---|---|---|---|
| `/devices` | `GET /api/hierarchy/kso-devices` | device_code, display_name, store, status, versions, screen geometry | No heartbeat, no auth status, no manifest/media readiness, no last_seen from heartbeat |
| `/readiness` | `GET /api/test-kso-readiness?device_code=...` | Test-kso readiness (backend health, device status, campaign/placement check) | **Test-kso only** — hardcoded device_code fallback. Not a real device dashboard. |
| `/dashboard` | Aggregates from campaigns/manifests endpoints | Campaign/placement KPI counts | No device status section |

**Assessment:** Portal `/devices` shows static registry — useful but incomplete. No page shows: heartbeat recency, credential expiry, manifest delivery status, media cache status, last PoP event time. No readiness badge per device.

### 1.5 BackendClient (Portal)

| Method | Endpoint |
|---|---|
| `list_kso_devices()` | `GET /api/hierarchy/kso-devices` |
| `get_test_kso_readiness()` | `GET /api/test-kso-readiness?device_code=...` |

**Missing:** No methods for gateway device list, heartbeat list, credential status, or device dashboard aggregation.

---

## 2. Pilot Dashboard Requirements

### 2.1 What a pilot operator needs to see

| Information | Current | Backend data |
|---|---|---|
| Device list with codes & store names | ✅ /devices | KsoDevice |
| Device status (active/inactive/disabled) | ✅ /devices | KsoDevice.status |
| Last heartbeat time & status | ❌ | DeviceHeartbeat.created_at, status |
| Auth credential status (active/expired) | ❌ | DeviceCredential.status, expires_at |
| Current manifest code | ❌ | DeviceHeartbeat.current_manifest_hash |
| Manifest delivery status (last request) | ❌ | DeviceManifestRequest.request_status |
| Media cache status (cached/total) | ❌ | DeviceHeartbeat.cache_items_count |
| Last PoP event time | ❌ | ProofOfPlayEvent.received_at |
| Sidecar version | ❌ (in KsoDevice but not updated) | KsoDevice.sidecar_version |
| Error log (recent device events) | ❌ | DeviceEvent (severity=error) |
| Readiness badge (ready/warning/blocked) | ❌ | Needs derivation |

### 2.2 Readiness Badge Logic

```
ready    = heartbeat recent (< 5 min) + credential active + manifest delivered + no critical errors
warning  = heartbeat seen (< 30 min) but stale (> 5 min) OR credential expiring within 7 days
blocked  = no heartbeat in 30 min OR credential expired OR critical error event in last hour
unknown  = no data (new device, never connected)
```

---

## 3. Gaps

### 🔴 GAP 1: No device dashboard aggregation endpoint

**Missing:** `GET /api/device-dashboard` returning per-device: status, last_heartbeat, credential_status, manifest_status, media_cache, last_pop_event, errors.

**Fix:** Create aggregation endpoint joining GatewayDevice ↔ DeviceHeartbeat ↔ DeviceCredential ↔ DeviceSession ↔ DeviceManifestRequest ↔ DeviceMediaRequest ↔ ProofOfPlayEvent. Apply safe projection (no secrets, no raw UUIDs in fields visible to UI).

### 🔴 GAP 2: Heartbeat does not carry sidecar status

Sidecar `agent_status.json` (running/warning/error, errors list) is **not** included in `DeviceHeartbeat`. Heartbeat payload is: `status`, `device_time`, `app_version`, `os_version`, `storage_free_mb`, `cache_items_count`, `current_manifest_hash`.

**Fix:** Extend heartbeat payload to include `sidecar_status` and optionally a truncated `errors` list (validated, no secrets).

### 🔴 GAP 3: KsoDevice.last_seen_at not updated by heartbeat

`KsoDevice.last_seen_at` is updated only via explicit `sync_device_metadata` — not from `DeviceHeartbeat`.

**Fix:** Backend heartbeat handler should also update `KsoDevice.last_seen_at` (and optionally `sidecar_version`, `manifest_version`) to keep the hierarchy registry current.

### 🟡 GAP 4: Readiness page is test-kso-only

`/readiness` uses `GET /api/test-kso-readiness?device_code=...` — hardcoded to test device. Not a production dashboard.

**Fix:** Replace with production device dashboard endpoint (GAP 1), or add a separate `/pilot-dashboard` page.

### 🟡 GAP 5: Portal `/devices` shows no gateway data

Shows KSO registry only — no heartbeat, credential, manifest, PoP info.

**Fix:** Either extend `/devices` to include gateway data (expensive — many joins) or add a new tab/column with dashboard data from GAP 1.

### 🟢 GAP 6: No manifest/media readiness per device

`DeviceHeartbeat.cache_items_count` exists but is not surfaced. No per-device manifest delivery status in portal.

**Fix:** Include in dashboard aggregation endpoint.

### 🟢 GAP 7: No error aggregation for operations

`DeviceEvent` table exists with `severity=error` events but no endpoint to list recent errors across all devices.

**Fix:** Add to dashboard aggregation, or add `GET /api/device-dashboard/errors?limit=50`.

---

## 4. Security Requirements

For all dashboard endpoints:

- ❌ No `secret_hash`, `access_token_hash`, `device_secret`
- ❌ No full `backend_url` in responses
- ❌ No `client_ip` in safe projection (may be logged, not shown)
- ❌ No raw UUIDs in fields visible to UI (use safe codes)
- ❌ No barcode/receipt/payment/fiscal/customer data
- ✅ Safe projection: device_code, status, timestamps, counts, versions
- ✅ Permission: `devices.gateway.read` or new `devices.dashboard.read`

---

## 5. Proposed Plan

### 39.4.1 — Backend Device Dashboard API

- Create aggregation endpoint: `GET /api/device-dashboard`
- Join GatewayDevice + latest heartbeat + credential status + manifest request + PoP
- Safe projection schema: `DeviceDashboardItem`
- Permission: `devices.dashboard.read`
- Extend heartbeat handler to update KsoDevice.last_seen_at
- Extend heartbeat payload schema to accept `sidecar_status`
- Backend tests: +15-20

### 39.4.2 — Portal Device Dashboard Page

- New page `/device-dashboard` or extend `/devices` with dashboard tab
- Fetch from `GET /api/device-dashboard`
- Show: device_code, status badge, last heartbeat (relative time), credential status, manifest status, media cache, last PoP, readiness badge
- Server-side only, no JS/CDN/localStorage
- Portal tests: +10-15

### 39.4.3 — Readiness Page Hardening

- Replace test-kso readiness with production device dashboard
- OR: repurpose `/readiness` as `/pilot-dashboard` with device list + readiness badges
- Remove hardcoded `test-dev-readiness` device_code

### 39.4.4 — Sidecar Heartbeat Contract Update (no KSO run)

- Update heartbeat payload model to include `sidecar_status`, `errors` (truncated)
- Update backend heartbeat handler to persist sidecar_status
- Sidecar agent test updates (no physical KSO required)
- Contract tests: sidecar heartbeat format validation

### 39.4.5 — Pilot Operator Dashboard Polish

- Readiness badge derivation: ready/warning/blocked/unknown
- Color-coded statuses
- Filter by store/branch
- Last errors section
- No physical KSO delivery in this step

---

## 6. Deferred (beyond 39.4)

| Item | Reason |
|---|---|
| Physical KSO delivery | Requires live fleet |
| Sidecar daemon auto-start | Requires KSO SSH |
| Real-time WebSocket push | Complexity, no JS requirement |
| Fleet-wide operations (restart/update) | Requires physical KSO |
| Hardware scanner validation | No scanner hardware |

---

## 7. Подтверждения

- ❌ КСО/SSH/X11/Chromium/runner/sidecar daemon/PoP не запускались
- ❌ Manifest на физическую КСО не публиковался
- ❌ Sidecar sync не запускался
- ❌ Secrets/full URLs/tokens/barcodes не выводились
- ✅ v0.9.0 и v0.10.0 tags не переписывались
