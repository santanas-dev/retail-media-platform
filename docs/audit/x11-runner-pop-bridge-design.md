# X11 Runner — PoP Event Queue / Backend Upload Bridge Design

**Status:** ✅ Implemented (38.2.3)
**Created:** 2026-06-24
**Scope:** Dev-only bridge — no KSO, no X11, no Chromium

## Purpose

Bridge between `ScreensaverPoPDraft` (X11 runner) and the sidecar's PoP pipeline
(`pop/pending/player_events.jsonl` → classifier → `PopPayloadEvent` → backend
`POST /device-gateway/kso/{device_code}/pop`).

## Architecture (after 38.2.3)

```
ScreensaverRunner → ScreensaverPoPDraft {creative_code, event_type, media_available, …}
    ↓  build_screensaver_pop_record()          [screensaver_pop_bridge.py]
    ↓  maps: screen_visible→impression, playback_completed→completed, blocked→blocked
    ↓
sidecar JSONL record {event_type, event_status, creative_code, media_available, …}
    ↓  written to pop/pending/player_events.jsonl  (via pop_writer.py compatible format)
    ↓
sidecar pop_pickup.py → classify_pop_event()
    ↓  CLASS_ELIGIBLE only when event_status=completed AND media_cache_complete
    ↓
pop_payload.py → PopPayloadEvent {creative_code, manifest_item_id, …}
    ↓  pop_sender.py → HTTP POST
    ↓
backend POST /device-gateway/kso/{device_code}/pop
    ↓  KsoPoPIngestRequest {event_code, media_ref, event_type, …}
    ↓  KsoProofOfPlayEvent {event_code, device_code, creative_code, …}
    ↓
portal / proof-of-play → filter by creative_code ✅
```

## Key Design Decisions

### 1. Event type mapping

| Screensaver event | Sidecar type | Status | Eligible for backend? |
|---|---|---|---|
| `screen_visible` | `impression` | `draft` | ❌ (diagnostic only) |
| `screen_hidden` | `completed` | `draft` | ❌ (diagnostic only) |
| `playback_started` | `playback_started` | `draft` | ❌ (requires media) |
| `playback_completed` | `playback_completed` | `completed` | ✅ (if media_available) |
| `blocked` | `blocked` | `draft` | ❌ (diagnostic) |

### 2. Media gate

- `playback_started`/`playback_completed` → **blocked** if `media_available=False`
- Only `playback_completed` with `media_available=True` produces `event_status=completed`
- Backend only ingests `completed` events (sidecar classifier rule)

### 3. creative_code chain

```
backend manifest item.creativeCode
  → PlayerPlaylistItem.creative_code
  → ScreensaverCreativePayload.creative_code
  → ScreensaverPoPDraft.creative_code
  → build_screensaver_pop_record().creative_code
  → JSONL record["creative_code"]
  → PopPayloadEvent.creative_code
  → backend KsoProofOfPlayEvent.creative_code
  → portal report filterable by creative_code
```

### 4. Backend compatibility

The backend `kso_proof_of_play_events` table already contains `creative_code` (migration 030).
The ingest endpoint `POST /device-gateway/kso/{device_code}/pop` accepts `KsoPoPIngestRequest`
which maps through sidecar's `PopPayloadEvent` → `PopPayloadEnvelope` → HTTP body.

Backend derives `creative_code` from placement chain server-side, but the `creative_code`
field in `PopPayloadEvent` provides a client-side correlation that can be used for
verification.

### 5. Idempotency

`build_screensaver_event_code()` generates deterministic codes:
- Format: `scr-{sha256[:16]}`
- Hash input: `creative_code|event_type|started_at|slot_order`
- Same input → same code (idempotent re-send)
- Backend enforces `event_code` UNIQUE constraint

### 6. Forbidden fields

JSONL records and all bridge output NEVER contain:
- `token`, `secret`, `password`, `api_key`, `device_secret`, `access_token`
- `backend_url`, `backend_base_url`
- `file_path`, `absolute_path`, `local_path`
- `sha256`, `storage_ref`, `minio`, `s3`
- `barcode`, `scanner`, `key_value`
- `receipt`, `payment`, `fiscal`, `customer`, `card`, `pan`, `phone`, `email`

### File Manifest

| File | Change | Description |
|------|--------|-------------|
| `apps/kso_player/kso_player/screensaver_pop_bridge.py` | NEW 320 | Bridge adapter |
| `apps/kso_player/kso_player/pop_writer.py` | +2 | Extended ALLOWED_RECORD_KEYS |
| `apps/kso_sidecar_agent/kso_sidecar_agent/pop_pickup.py` | +4 | Extended ALLOWED_RECORD_KEYS + ALLOWED_EVENT_TYPES |
| `apps/kso_sidecar_agent/kso_sidecar_agent/pop_payload.py` | +2 | creative_code in PopPayloadEvent + builder |
| `apps/kso_sidecar_agent/kso_sidecar_agent/pop_send_package.py` | +1 | creative_code in builder |
| `apps/kso_player/tests/test_screensaver_pop_bridge.py` | NEW | 44 tests |
| `apps/kso_player/tests/test_pop_writer.py` | +2/−3 | Optional keys test fix |

### Backward Compatibility

All extensions are optional — `creative_code` and `media_available` are
NOT required in existing records. Sidecar classifier handles missing fields
gracefully (they default to None/0). Existing Chromium player PoP pipeline
is unaffected.

### 38.2.4 — E2E Validation (2026-06-24)

- Full 9-step chain validated with synthetic data
- creative_code preserved: manifest → playlist → creative → availability → PoP → JSONL → sidecar → PopPayloadEvent → backend/portal
- 31 E2E tests: happy path, negative paths, security audit, backend/portal compat
- Security: no forbidden fields in any user-facing output
- Backend schema compatibility confirmed (KsoPoPIngestRequest/Response, KsoPoPListResponse)
- Portal filter by creative_code confirmed compatible

### Safety Constraints (unchanged)

- ❌ KSO 192.168.110.223 not touched
- ❌ Physical run / X11 / Chromium not launched
- ❌ UKM5 / Openbox / systemd / .profile unchanged
- ❌ No backend URLs, tokens, secrets added
- ❌ No receipt/fiscal/customer data in any output
