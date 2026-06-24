# X11 Runner PoP Reporting E2E Validation

**Status:** ✅ Validated (38.2.4)
**Created:** 2026-06-24
**Scope:** Dev-only — no KSO, no X11, no Chromium, no backend server

## Purpose

End-to-end validation of the entire chain from backend manifest `creativeCode`
to portal proof-of-play report, using only synthetic/dev test data.

## Validated Chain (9 steps)

```
Step 1: PlayerPlaylistItem.creative_code       ← backend manifest item.creativeCode
Step 2: ScreensaverCreativePayload             ← build_screensaver_creative()
Step 3: ScreensaverMediaAvailability           ← check_screensaver_media_availability()
Step 4: decide_creative_visibility()           ← state=idle, kill_switch=inactive
Step 5: ScreensaverPoPDraft                    ← build_screensaver_pop_draft()
Step 6: Bridge JSONL record                    ← build_screensaver_pop_record()
Step 7: pop/pending/player_events.jsonl        ← JSONL write
Step 8: Sidecar classify_pop_event()           → CLASS_ELIGIBLE
Step 9: PopPayloadEvent.creative_code          → backend/portal compatible
```

**All 9 steps preserve creative_code.** Tested with `"e2e-trace-promo-2025"`.

## Happy Path Results

| Step | Component | Result |
|------|-----------|--------|
| 1 | PlaylistItem | ✅ creative_code present |
| 2 | CreativePayload | ✅ not synthetic, valid |
| 3 | MediaAvailability | ✅ media_available, ready_for_runner |
| 4 | Visibility | ✅ visible (VIS_REASON_CREATIVE_VALID) |
| 5 | PoPDraft | ✅ creative_code + media_available=True |
| 6 | Bridge record | ✅ event_type=playback_completed, status=completed |
| 7 | JSONL write | ✅ record written, readable with creative_code |
| 8 | Sidecar classify | ✅ CLASS_ELIGIBLE (completed + media) |
| 9 | PopPayloadEvent | ✅ creative_code="summer-promo-v3" |

## Negative Paths

| Scenario | Expected | Result |
|----------|----------|--------|
| media_available=False + playback_completed | → blocked, event_status=draft | ✅ |
| media_available=False + playback_started | → blocked, event_status=draft | ✅ |
| Blocked event | → draft only, not eligible | ✅ |
| kill_switch_active | → hidden_kill_switch | ✅ |
| non-idle state (transaction/payment/receipt/service) | → hidden_state | ✅ |
| missing creative_code in PlaylistItem | → synthetic fallback, is_synthetic=True | ✅ |

## Security Audit

All user-facing outputs checked for forbidden fields:

| Output | Forbidden check |
|--------|:---:|
| ScreensaverCreativePayload.to_safe_dict() | ✅ clean |
| ScreensaverMediaAvailability.to_safe_dict() | ✅ clean |
| ScreensaverPoPDraft.to_safe_dict() | ✅ clean |
| Bridge JSONL record | ✅ clean |
| ScreensaverPopRecordResult.to_safe_dict() | ✅ clean |
| No raw UUIDs in user-facing output | ✅ confirmed |

**Forbidden:** barcode, scanner, key_value, receipt, payment, fiscal, customer,
card, pan, phone, email, file_path, absolute_path, sha256, storage_ref, minio, s3,
backend_url, token, secret, device_secret.

## Backend Compatibility

- `KsoPoPIngestRequest` — ✅ accepts event_code, media_ref, event_type, duration_ms
- `KsoPoPIngestResponse` — ✅ contains creative_code, device_code, placement_code, campaign_code
- `KsoPoPListResponse` — ✅ contains creative_code, filterable by portal
- `PopPayloadEvent` — ✅ has creative_code field (new in 38.2.3)
- `KsoProofOfPlayEvent` — ✅ table has creative_code column (migration 030)
- Backend model has NO forbidden columns ✅

## Portal Compatibility

- `list_kso_pop_events()` accepts `creative_code` filter parameter ✅
- `KsoPoPListResponse` safe projection — no raw UUIDs, no secrets ✅
- Portal can filter: `GET /api/proof-of-play/kso/events?creative_code=summer-promo-v3` ✅

## Test Coverage

31 tests: 9 happy path steps + 6 negative paths + 6 security audit + 5 backend compat + 2 portal compat + 1 full 9-step trace + 2 additional checks.

## Design Note: Backend Ingest Requires Separate Step

The backend `POST /device-gateway/kso/{device_code}/pop` endpoint requires:
- Running PostgreSQL + KSO device + published manifest + placement → campaign → creative chain
- This is a backend integration test, not a unit test

Current validation covers **schema compatibility** — all fields match.
Full backend ingest with real DB is a separate integration test step.

### 38.2.5 — Backend Ingest + Portal Integration (2026-06-24)

- Backend service test (mock DB): 18 tests — creative_code through ingest/response,
  idempotency, list filters, safety audit, blocked/draft handling
- `ingest_kso_pop()` returns `creative_code` from placement→campaign→creative chain ✅
- Duplicate `event_code` → idempotent accepted ✅
- `list_kso_pop_events(creative_code=…)` filter works ✅
- All filter combinations tested: device_code, campaign_code, creative_code, placement_code ✅
- Blocked event_type stored as `accepted` (backend doesn't reject) ✅
- Ingest response: 0 forbidden fields (6 safe fields only) ✅
- List response: 0 forbidden fields (11 safe fields only) ✅
- Portal template: creative_code filter + column already present ✅
- Backend not started — all tests use `AsyncMock` (no real DB) ✅

### Safety Constraints (unchanged)

- ❌ KSO 192.168.110.223 not touched
- ❌ Physical run / X11 / Chromium not launched
- ❌ UKM5 / Openbox / systemd / .profile unchanged
- ❌ No backend URLs, tokens, secrets added
- ❌ No receipt/fiscal/customer data in any output
- ✅ All test data is synthetic — no real manifest IDs, no real device codes
