# X11 Runner — Sidecar Cache Bridge Design

**Status:** ✅ Implemented (38.2.2)
**Created:** 2026-06-24
**Scope:** Dev-only bridge — no KSO, no X11, no Chromium

## Purpose

Bridge between sidecar's local `media/current/` cache and X11 screensaver runner,
enabling the runner to check whether a `ScreensaverCreativePayload` has actual
media available locally before attempting to display it.

## Architecture Gap (before 38.2.2)

```
sidecar manifest (current_manifest.json) → PlayerPlaylist → ScreensaverCreativePayload
                                                                    ↓
                                          X11 Runner receives creative with media_ref
                                          BUT: no check whether media/current/<file> exists
```

`decide_creative_visibility()` checked:
- kill_switch
- KSO state (idle/non-idle)
- playlist readiness
- creative validity
- creative expiration

…but **NOT** media file existence. Runner could receive a creative whose
media hadn't been downloaded yet (or was corrupted/missing).

## Solution (38.2.2)

### New module: `screensaver_media_availability.py`

```
ScreensaverCreativePayload
    ↓  check_screensaver_media_availability(creative, agent_root)
    ↓
    ├─ Validate media_ref safety (pattern, no forbidden substrings)
    ├─ Read manifest/current_manifest.json
    ├─ Find manifest item by slot_order → filename
    ├─ Check media/current/<filename> existence
    │   ├─ Symlink → rejected (INVALID_MEDIA_REF)
    │   ├─ Missing → MEDIA_MISSING
    │   ├─ Directory → MEDIA_FILE_CORRUPT
    │   └─ File exists → MEDIA_AVAILABLE
    ↓
ScreensaverMediaAvailability {ready_for_runner, media_available, reason, ...}
    ↓  decide_creative_visibility(creative, media_availability=avail)
    ↓
    ├─ ready_for_runner=True  → VIS_REASON_CREATIVE_VALID (visible)
    ├─ media missing          → VIS_REASON_MEDIA_MISSING
    ├─ invalid ref            → VIS_REASON_INVALID_MEDIA_REF
    └─ cache unavailable      → VIS_REASON_CACHE_UNAVAILABLE
    ↓
ScreensaverPoPDraft {..., media_available}
```

### Key Design Decisions

1. **Dev-only bridge** — no physical KSO access. `agent_root` parameter accepts
   a local path for testing. On real KSO, the sidecar's agent_root would be
   injected at runtime.

2. **Slot-order lookup** — maps creative's `slot_order` → manifest item's `order`
   → `filename` in `current_manifest.json`. Does NOT use `media_ref` alias
   directly (which is `slot-NNN` — not a real filename).

3. **Existence-only check** — does NOT verify sha256 or size. This is a
   lightweight bridge; full integrity verification is the sidecar's
   responsibility (`media_cache.verify_media_file`).

4. **Synthetic creatives allowed** — test/fallback creatives with
   `is_synthetic=True` pass availability check even without real media files.

5. **Security gates** — symlinks rejected, path traversal rejected,
   absolute paths rejected, forbidden patterns in media_ref rejected.

### Forbidden Fields

`ScreensaverMediaAvailability` NEVER contains:
- `file_path`, `absolute_path`, `storage_ref`, `sha256`, `minio`, `s3`
- `backend_url`, `token`, `secret`, `device_secret`
- `receipt`, `payment`, `fiscal`, `customer`, `card`, `barcode`

### Integration Points

| Component | Change |
|-----------|--------|
| `screensaver_creative.py` | +`media_availability` param in `decide_creative_visibility()` |
| `screensaver_creative.py` | +`media_available` field in `ScreensaverPoPDraft` |
| `screensaver_creative.py` | +`SCREENSAVER_EVENT_BLOCKED` event type |
| `screensaver_creative.py` | +3 visibility reasons: `MEDIA_MISSING`, `INVALID_MEDIA_REF`, `CACHE_UNAVAILABLE` |

### File Manifest

| File | Lines | Description |
|------|-------|-------------|
| `apps/kso_player/kso_player/screensaver_media_availability.py` | NEW | Bridge module |
| `apps/kso_player/kso_player/screensaver_creative.py` | +52/−8 | Media gate + PoP fields |
| `apps/kso_player/tests/test_screensaver_media_availability.py` | NEW | 59 tests |
| `apps/kso_player/tests/test_screensaver_creative.py` | +2/−1 | Event types update |

### Journal — 38.2.3 (2026-06-24)

- **38.2.3 — PoP Event Queue Bridge**: `screensaver_pop_bridge.py` created.
  ScreensaverPoPDraft → sidecar JSONL record adapter.
  Creative_code carried through to backend PoP ingest.
  Media gate: playback blocked without media_available.
  +44 tests. Sidecar ALLOWED_RECORD_KEYS/ALLOWED_EVENT_TYPES extended.
  Backend `kso_proof_of_play_events` already has `creative_code` field.

### Safety Constraints (unchanged)

- ❌ KSO 192.168.110.223 not touched
- ❌ Physical run / X11 / Chromium not launched
- ❌ UKM5 / Openbox / systemd / .profile unchanged
- ❌ No backend URLs, tokens, secrets added
- ❌ No receipt/fiscal/customer data in any output
