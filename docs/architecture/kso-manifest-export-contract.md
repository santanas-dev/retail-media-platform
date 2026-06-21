# KSO Manifest Export Contract

**Version:** 1.0
**Date:** 2026-06-21
**Scope:** Block 28 — Portal to KSO Manifest
**Status:** Draft (audit)

## 1. Purpose

Define how the Retail Media Platform portal exports a safe, player-visible KSO manifest from existing backend entities (campaigns, creatives, bookings, schedule, publications, device gateway). This manifest is what the sidecar agent fetches and stores locally, and the KSO player reads to render advertising content.

## 2. v1 Scope

### In scope

| Entity | Role |
|---|---|
| KSO channel (`code = "kso"`) | Only channel in v1 manifest |
| ServPlus Sherman-J 5.1 | Physical KSO terminal |
| Linux OS | Target OS |
| СуперМаг УКМ 4 | POS integration |
| 1920×1080 screen | Physical resolution |
| 1440×1080 ad zone (left) | KSO player render area |
| 480×1080 UKM 4 zone (right) | POS UI — not in manifest |
| Chromium kiosk-mode | Future production player |
| Sidecar agent | Fetches manifest + media |
| Proof of Play | Backend correlation through internal IDs |

### Out of scope for v1

| Channel | Status |
|---|---|
| `android_tv` | ❌ Excluded |
| `led_shelf_banner` | ❌ Excluded |
| `price_checker` | ❌ Excluded |
| `esl` (electronic price tags) | ❌ Excluded |
| Mobile app as ad channel | ❌ Excluded |

## 3. Existing Backend Pipeline (Analysis)

The portal already has a full manifest generation pipeline. KSO manifest export is a **filtered projection** of existing data — not a new pipeline.

### Entity chain

```
organization                campaigns             media
  branches                    ├─ campaign_channels    creatives
  clusters                    ├─ campaign_targets      creative_versions
  stores (code: ^[a-z0-9_-]+$) ├─ campaign_renditions    renditions
     │                        │                         (per channel + profile)
     │                        ▼
     │                        │
     ▼                     inventory                   device_gateway
channels                   inventory_units              gateway_devices
  device_types               capacity_rules               device_credentials
  capability_profiles          │                          device_sessions
  physical_devices             ▼
  logical_carriers         bookings
  display_surfaces          campaign_bookings
     │                        booking_items
     │                          │
     │                          ▼
     │                      scheduling
     │                        schedule_runs
     │                        schedule_items
     │                          │
     │                          ▼
     │                      publications
     │                        publication_batches
     │                        publication_targets
     │                        manifest_versions (JSONB)
     │                        manifest_items
     │                          │
     │                          ▼
     └────────────────────── device-gateway
                              GET /api/device-gateway/manifest/current
                              GET /api/device-gateway/media/{manifest_item_id}
```

### Key existing components

| Component | Path | Status |
|---|---|---|
| Publication system | `backend/app/domains/publications/` | ✅ Implemented (Step 9) |
| Manifest generation | `publication_batches → manifest_versions.manifest_json` | ✅ Implemented |
| Device Gateway | `backend/app/domains/device_gateway/` | ✅ Implemented (Steps 10–13) |
| Manifest delivery | `GET /api/device-gateway/manifest/current` | ✅ Implemented (Step 11) |
| Media delivery | `GET /api/device-gateway/media/{id}` | ✅ Implemented (Step 12) |
| PoP ingest | `POST /api/device-gateway/pop/events` | ✅ Implemented (Step 13) |
| Campaign reports | `GET /api/campaign-reports/` | ✅ Implemented (Step 22) |

### Current manifest_json structure (publications)

The portal's internal `manifest_versions.manifest_json` (Step 9) contains:

```json
{
  "manifest_version": 1,
  "batch_id": "<uuid>",
  "target_id": "<uuid>",
  "inventory_unit": {"id": "<uuid>", "code": "safe_code"},
  "logical_carrier_id": "<uuid>",
  "display_surface_id": "<uuid>",
  "store": {"id": "<uuid>", "code": "safe_code"},
  "channel": {"id": "<uuid>", "code": "in-store-display"},
  "schedule": {
    "items": [
      {
        "date": "2026-06-18",
        "time_from": "08:00:00",
        "time_to": "08:00:15",
        "loop_position": 2,
        "spot_position": 3,
        "media": {
          "path": "creatives/abc/v1/uuid.webp",
          "sha256": "deadbeef...",
          "mime_type": "image/png",
          "width": 1920,
          "height": 1080,
          "duration_seconds": null
        },
        "campaign": {"id": "<uuid>", "code": "summer-promo"},
        "rendition_id": "<uuid>",
        "campaign_rendition_id": "<uuid>"
      }
    ]
  }
}
```

### Gap: internal → safe player manifest

The portal manifest_json carries **internal IDs** (`batch_id`, `target_id`, `campaign.id`, `rendition_id`), **MinIO paths** (`media.path`), and **internal codes** — all unacceptable for the player.

The KSO manifest export is a **safe projection** that strips internal fields and produces the player contract.

## 4. KSO Player Manifest Format

### Safe public manifest (player-readable)

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-06-21T12:00:00Z",
  "channel": "kso",
  "storeCode": "safe_store_code",
  "deviceCode": "safe_device_code",
  "items": [
    {
      "slotOrder": 0,
      "contentType": "image/png",
      "durationMs": 5000,
      "mediaRef": "media/current/slot-000",
      "validFrom": "2026-06-20T00:00:00Z",
      "validTo": "2026-06-30T23:59:59Z"
    }
  ]
}
```

### Field specifications

| Field | Type | Source | Notes |
|---|---|---|---|
| `schemaVersion` | int | Fixed: 1 | Manifest format version |
| `generatedAt` | ISO8601 | `now()` at export time | When the manifest was produced |
| `channel` | str | Fixed: `"kso"` | Only KSO in v1 |
| `storeCode` | str | `stores.code` | Safe code, `^[a-z0-9_-]+$` |
| `deviceCode` | str | `gateway_devices.device_code` | KSO device login |
| `items[].slotOrder` | int | Derived from `spot_position` or generated | 0-indexed, sequential |
| `items[].contentType` | str | `renditions.mime_type` | Only `image/png`, `image/jpeg`, `video/mp4`, `video/webm` |
| `items[].durationMs` | int | `schedule_items.spot_duration_seconds * 1000` | Milliseconds |
| `items[].mediaRef` | str | Generated: `media/current/slot-{slotOrder:03d}` | Safe alias, not real path |
| `items[].validFrom` | ISO8601 | `schedule_items.date + time_from` | When item becomes active |
| `items[].validTo` | ISO8601 | `schedule_items.date + time_to` | When item expires |

### Forbidden in player manifest

These fields MUST NOT appear in any player-facing manifest:

| Category | Forbidden fields |
|---|---|
| Authentication | `token`, `jwt`, `secret`, `api_key`, `password`, `credential`, `authorization`, `cookie`, `access_token`, `refresh_token` |
| Internal IDs | `manifest_item_id`, `campaign_id`, `creative_id`, `rendition_id`, `campaign_rendition_id`, `schedule_item_id`, `batch_id`, `target_id`, `booking_id`, `inventory_unit_id` |
| Backend | `backend_base_url`, `127.0.0.1`, `device_code` (except top-level `deviceCode`), `device_secret` |
| Paths | `file_path`, `media_path`, `local_path`, `creatives/`, `minio://`, `s3://`, absolute paths, real filenames |
| Media bytes | Raw media content, `media_bytes`, `sha256` (only used server-side for integrity verification) |
| Financial | `budget`, `currency`, `price`, `rate` |
| Customer/PII | `customer_id`, `phone`, `email`, `receipt_data`, `card_number`, `pan`, `fiscal_data` |

## 5. Backend → Player Mapping

### High-level mapping

| Portal entity | Player manifest field | Transformation |
|---|---|---|
| `campaigns` (status=`approved`) | Items included only if active | Filter: inactive → excluded |
| `campaign_channels` (channel=`kso`) | `channel: "kso"` | Filter: non-KSO → excluded |
| `schedule_runs` (status=`approved`) | Source for items | Only approved runs |
| `schedule_items` (status=`active`) | `slotOrder`, `validFrom`, `validTo` | Items → ordered slots |
| `renditions` (status=`valid`) | `contentType`, `durationMs` | Filter: invalid → excluded |
| `creatives` (status=`approved`) | Prerequisite for rendition | Non-approved → excluded |
| `publication_batches` (status=`published`) | Gate: only published | Draft/cancelled → excluded |
| `manifest_versions.manifest_json` | Source of schedule data | Strip internal IDs |
| `stores.code` | `storeCode` | Safe code only, no UUID |
| `gateway_devices.device_code` | `deviceCode` | Safe code only, no UUID |
| MinIO `creatives/{id}/v/{uuid}.ext` | Server-side only | **Never** in manifest; delivered via `GET /api/device-gateway/media/{id}` separately |

### Safety rules for KSO export builder

The export builder (future code — NOT in this step) MUST:

1. **Include only:**
   - Active campaigns with `status = "approved"`
   - KSO channel only (`campaign_channels.channel.code = "kso"`)
   - Approved creatives (`creatives.status = "approved"`)
   - Valid renditions (`renditions.status = "valid"`, MIME in allowlist)
   - Published manifests (`publication_batches.status = "published"`)
   - Active gateway devices (`status IN (pending, active, lost)`)
   - Active stores (`stores.is_active = true`)

2. **Exclude:**
   - Expired bookings (`date_to < now`)
   - Future-only bookings (starts after manifest validity window)
   - Unsupported MIME types (SVG, HTML, JS, ZIP, etc.)
   - Missing media (MinIO object not found)
   - Non-KSO devices (gateway_devices.channel_id ≠ kso)
   - Disabled/retired devices
   - Duplicate slot orders
   - Campaigns without approved schedule

3. **Validate:**
   - `slotOrder` is unique within manifest
   - `durationMs > 0` and `≤ 86_400_000` (24h)
   - `validFrom < validTo`
   - `contentType` in allowlist: `image/png`, `image/jpeg`, `video/mp4`, `video/webm`
   - `storeCode` matches `^[a-z0-9_-]+$`
   - JSON does not exceed size limit (10 MB)

## 6. Sidecar → Player Delivery Model

```
┌─────────────────────────────────────────────────────────────┐
│ Portal Backend                                              │
│   GET /api/device-gateway/manifest/current                  │
│   GET /api/device-gateway/media/{manifest_item_id}          │
└─────────────────┬───────────────────────────────────────────┘
                  │ (HTTPS, device JWT)
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ KSO Sidecar Agent (on device)                               │
│   sync-manifest → manifest/current_manifest.json            │
│   sync-media   → media/current/{slot-XXX} + .sha256         │
└─────────────────┬───────────────────────────────────────────┘
                  │ (local filesystem, NO network)
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ KSO Player (Chromium kiosk)                                 │
│   build_playlist() → reads manifest/ + media/               │
│   shell_snapshot → bootstrap_snapshot.js                    │
│   render: 1440×1080 ad zone                                 │
└─────────────────────────────────────────────────────────────┘
```

### Player reads (local only)

- `manifest/current_manifest.json` — the safe public manifest
- `media/current/slot-{order:03d}` — media files (symlinks or copies)
- `media/current/slot-{order:03d}.sha256` — integrity checksums

### Player NEVER accesses

- Backend HTTP endpoints
- Device gateway
- MinIO/S3
- `device_secret`, `token`, `config.json`
- `kso_state.json` (read by player, **written** by UKM 4 state adapter)
- PoP endpoints

## 7. PoP Correlation (Server-Side Only)

### Problem

Player writes safe PoP events without campaign IDs. Backend needs to correlate PoP with campaigns for reporting.

### Solution: server-side internal mapping

PoP event from player:
```json
{
  "slotOrder": 0,
  "playedAt": "ISO8601",
  "durationMs": 5000,
  "playStatus": "completed"
}
```

Server internal mapping (stored in `manifest_items`):
```
slotOrder=0 → manifest_item_id → schedule_item_id → campaign_id → creative_id
```

The portal's `proof_of_play_events` table already stores this mapping:

| Field | Source |
|---|---|
| `manifest_item_id` | From device PoP request |
| `campaign_id` | Server-filled from `manifest_items` |
| `campaign_rendition_id` | Server-filled from `manifest_items` |
| `rendition_id` | Server-filled from `manifest_items` |
| `creative_version_id` | Server-filled from `manifest_items` |

**Player NEVER sees these IDs.** They are populated server-side on PoP ingest.

This is already implemented in Step 13 (`POP Ingest Core`).

## 8. Device Gateway Endpoint

### Existing

`GET /api/device-gateway/manifest/current?current_manifest_hash=...`

### Proposed KSO-specific (optional, future)

`GET /api/device-gateway/kso/manifest?current_manifest_hash=...`

Both serve published manifests. The KSO-specific variant could:
- Pre-filter by `channel = "kso"`
- Strip internal IDs at the gateway layer
- Return the safe player format directly

### Decision: reuse existing endpoint

The existing `GET /api/device-gateway/manifest/current` already serves manifests to devices. The KSO player manifest is a **projection** of the existing `manifest_json` — either:

**Option A:** Transform at export time (publication → safe manifest stored separately)
**Option B:** Transform at gateway delivery time (strip IDs on response)

Recommendation: **Option A** — add a `kso_manifest_json` column to `manifest_versions` or create a separate KSO export step that produces the safe player format at publication time. This keeps gateway delivery fast (no per-request transformation) and allows the safe format to be audited/approved before delivery.

## 9. Database Impact Assessment

### No schema changes required for v1

The existing data model already supports KSO manifest export:

| Requirement | Covered by | Status |
|---|---|---|
| Campaign → channel filter | `campaign_channels` + `channels.code` | ✅ |
| Campaign → creative → rendition | `campaign_renditions` → `renditions` | ✅ |
| Schedule → slots | `schedule_items` | ✅ |
| Publication → manifest | `publication_batches` → `manifest_versions.manifest_json` | ✅ |
| Device → store → channel | `gateway_devices` | ✅ |
| PoP → campaign correlation | `manifest_items` → `proof_of_play_events` | ✅ |

### Optional future additions

- `manifest_versions.kso_manifest_json` (JSONB) — safe player manifest, pre-computed
- `manifest_versions.kso_manifest_hash` (VARCHAR 64) — SHA-256 for not-modified checks
- Index on `publication_targets(channel_id, store_id)` for KSO-only queries

**No migrations needed for contract definition.** These are future implementation decisions.

## 10. Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Manifest size grows with many items | Cap at 10 MB / 1000 items |
| 2 | Slot order collisions across campaigns | Server-side sequential ordering |
| 3 | Timezone handling (store timezone vs UTC) | Use UTC in manifest, player adjusts |
| 4 | Partial media delivery (some files missing) | Sidecar sync validates; player holds if incomplete |
| 5 | Manifest version mismatch (race) | ETag/hash-based not-modified; atomic local swap |
| 6 | Internal ID leak through error messages | Strict output safety rules (forbidden field check at gateway) |
| 7 | Channel misconfiguration (non-KSO device gets KSO manifest) | Gateway match logic enforces channel_id (already implemented) |

### Open questions

- Should `validFrom`/`validTo` use store-local time or UTC?
  - Recommendation: UTC in manifest, player applies local timezone if needed
- How many slot items per manifest? Expected range?
  - Estimate: 10–200 slots per KSO device per day (based on loop_duration / spot_duration)

## 11. What Is NOT Done in This Step

- ❌ Writing manifest export builder code
- ❌ Database migrations
- ❌ New API endpoints
- ❌ Changes to player or sidecar
- ❌ Android TV / LED / ESL / mobile app manifest
- ❌ Windows Service / MSI
- ❌ Real backend integration

## 12. Next Steps (Block 28+)

1. **28.2** — KSO manifest export mini-design (builder code design)
2. **28.3** — KSO manifest export service implementation
3. **28.4** — Gateway integration (serve KSO-safe manifest)
4. **28.5** — End-to-end smoke: portal → sidecar → player
5. **28.6** — PoP correlation verification

## References

- `docs/publications.md` — Manifest generation and publication
- `docs/device_gateway.md` — Device-facing API, manifest/media delivery
- `docs/campaigns.md` — Campaign lifecycle
- `docs/media.md` — Creative, rendition, validation
- `docs/inventory.md` — Booking and scheduling pipeline
- `docs/campaign_reporting.md` — PoP correlation
- `docs/architecture.md` — System domains
- `docs/domains.md` — Domain inventory
- `apps/kso_player/README.md` — Player manifest contract (slot-based format)
