# Proof Event v1 — Schema Specification

**Version:** 1.0
**Phase:** 0 (Architecture Lock)
**Source:** ТЗ v2.5 Table 15; §11.1, §24.8

---

## Purpose

Proof Events are the canonical evidence of ad delivery. Each event is a cryptographically verifiable record that a specific creative was displayed on a specific device at a specific time. Events are batched for efficiency, idempotent for reliable delivery, and normalized across all channel types.

## Schema (v1.0)

### Individual Event (within a batch)

```json
{
  "event_id": "uuid",
  "event_type": "proof",
  "schema_version": "1.0",
  "device": {
    "device_id": "uuid",
    "device_code": "KSO-003",
    "serial_number": "SN-12345",
    "hardware_fingerprint": "sha256:fingerprint..."
  },
  "store": {
    "store_id": "uuid",
    "store_code": "ST-042"
  },
  "campaign": {
    "campaign_id": "uuid",
    "campaign_code": "CAMP-2026-001"
  },
  "placement": {
    "placement_id": "uuid",
    "placement_code": "PLC-2026-042"
  },
  "creative": {
    "creative_version_id": "uuid",
    "media_asset_id": "uuid",
    "rendition_id": "uuid (optional)",
    "display_name": "Brand X Summer Ad v3"
  },
  "manifest": {
    "manifest_id": "uuid",
    "manifest_version": 3
  },
  "surface": {
    "surface_id": "uuid (optional)",
    "surface_code": "SURF-001 (optional)",
    "zone_id": "ad_zone (optional)",
    "channel_type": "KSO|ANDROID_TV|PRICE_CHECKER|ESL|LED",
    "device_type": "KSO_V1|ANDROID_TV_V1|PRICE_CHECKER_V1|ESL_GW_V1|LED_CTRL_V1"
  },
  "playback": {
    "started_at": "2026-07-02T08:00:00.000Z",
    "ended_at": "2026-07-02T08:00:10.000Z",
    "duration_ms": 10000,
    "media_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "verified_sha256": true
  },
  "result": {
    "playback_result": "success|skipped|failed|interrupted",
    "failure_reason": "offline|missing_file|sha256_mismatch|manifest_expired|playback_error|hidden_by_touch|hidden_by_ukm4_activity|player_crash",
    "failure_detail": "string (human-readable)"
  },
  "proof": {
    "pop_mode": "real_playback|screen_render|idle_screen|template_applied|gateway_ack|label_ack|controller_ack",
    "device_signature": "base64-encoded Ed25519 or HMAC signature",
    "signature_algorithm": "Ed25519|HMAC-SHA256"
  },
  "timestamps": {
    "event_recorded_at": "2026-07-02T08:00:15Z",
    "event_sent_at": "2026-07-02T08:01:00Z"
  },
  "batch": {
    "batch_id": "uuid",
    "batch_sequence": 142
  },
  "correlation_id": "uuid"
}
```

### Batch Wrapper

```json
{
  "batch_id": "uuid",
  "device_id": "uuid",
  "device_code": "KSO-003",
  "batch_sequence": 142,
  "events": [ ... ],
  "events_count": 15,
  "sent_at": "2026-07-02T08:01:00Z",
  "correlation_id": "uuid",
  "signature": {
    "algorithm": "Ed25519",
    "value": "base64-encoded-signature-over-entire-batch",
    "device_public_key_fingerprint": "SHA256:abc123..."
  }
}
```

---

## Field-Level Description

| Path | Type | Required | Description |
|------|------|----------|-------------|
| `event_id` | UUID | Yes | Globally unique, idempotent key |
| `event_type` | string | Yes | Always "proof" for v1 |
| `schema_version` | string | Yes | Schema version for forward compat |
| `device.device_id` | UUID | Yes | Device UUID |
| `device.device_code` | string | Yes | Human-readable device code |
| `device.serial_number` | string | No | Physical serial number |
| `device.hardware_fingerprint` | string | No | SHA-256 of hardware identifiers |
| `store.store_id` | UUID | Yes | Store where device is located |
| `campaign.campaign_id` | UUID | Yes | Owning campaign |
| `campaign.campaign_code` | string | Yes | Human-readable code |
| `placement.placement_id` | UUID | Yes | Owning placement |
| `creative.creative_version_id` | UUID | Yes | Version of creative displayed |
| `creative.media_asset_id` | UUID | Yes | Media asset file |
| `manifest.manifest_id` | UUID | Yes | Manifest that scheduled this play |
| `manifest.manifest_version` | int | Yes | Manifest version number |
| `surface.surface_id` | UUID | No | Display surface (for multi-surface) |
| `surface.channel_type` | enum | Yes | Channel classification |
| `surface.device_type` | enum | Yes | Specific device type |
| `playback.started_at` | ISO 8601 | Yes | When play started |
| `playback.ended_at` | ISO 8601 | No | When play ended (null if interrupted) |
| `playback.duration_ms` | int | Yes | Duration in milliseconds |
| `playback.media_sha256` | string | Yes | SHA-256 verified before play |
| `playback.verified_sha256` | bool | Yes | Was hash verified successfully |
| `result.playback_result` | enum | Yes | success, skipped, failed, interrupted |
| `result.failure_reason` | enum | No | Categorized failure reason |
| `proof.pop_mode` | enum | Yes | Type of proof evidence |
| `proof.device_signature` | string | Yes | Cryptographic signature by device |
| `proof.signature_algorithm` | enum | Yes | Ed25519 or HMAC-SHA256 |
| `timestamps.event_recorded_at` | ISO 8601 | Yes | When player recorded this event |
| `timestamps.event_sent_at` | ISO 8601 | Yes | When batch was sent to server |
| `batch.batch_id` | UUID | Yes | Batch this event belongs to |
| `batch.batch_sequence` | int | Yes | Monotonically increasing per device |

---

## Proof Modes (pop_mode)

| Mode | Channel | Evidence | Description |
|------|---------|----------|-------------|
| `real_playback` | KSO, Android TV | Chromium/player API callback | Actual render event with start/end time |
| `screen_render` | Android TV, WebOS | System-level render notification | Screen was displaying the content |
| `idle_screen` | Price Checker | App lifecycle event | Ad shown during idle/screensaver |
| `template_applied` | ESL (template-based) | Gateway confirmation | Template was rendered on labels |
| `gateway_ack` | ESL, LED (vendor API) | Vendor API response | Gateway confirms delivery |
| `label_ack` | ESL (per-label) | ESL gateway per-label ACK | Individual label confirmed |
| `controller_ack` | LED (controller) | LED controller ACK | Controller confirms display |

## Failure Reasons

| Reason | Description |
|--------|-------------|
| `offline` | Device lost network connection |
| `missing_file` | Media file not found in cache |
| `sha256_mismatch` | Downloaded file hash doesn't match manifest |
| `manifest_expired` | Manifest `valid_to` has passed |
| `playback_error` | Player runtime error (Chromium crash, codec error) |
| `hidden_by_touch` | User touched screen, ad hidden |
| `hidden_by_ukm4_activity` | Cash register (УКМ4) activity triggered hide |
| `player_crash` | Player process terminated unexpectedly |

## Idempotency & Deduplication

1. **`event_id`** is the deduplication key. Server rejects duplicates with 409 Conflict.
2. **`batch_sequence`** allows gap detection: server expects monotonically increasing sequence per device.
3. **Gap recovery:** If server detects gap (e.g., received sequences 142, 144), it requests resend of 143 via device command `resend_batch`.
4. **Local buffer:** Device stores unsent batches locally. Oldest-first, bounded by disk space. Discards only after server ACK.

## Security

1. **Batch signature:** Entire batch payload signed with device's private key (Ed25519) or HMAC with device secret.
2. **Individual event signature:** Each event also carries a device signature for per-event verification.
3. **Signature verification:** PoP Ingestor verifies both batch-level and per-event signatures before enqueuing.
4. **Replay protection:** `event_id` + `batch_sequence` checked against Redis/ClickHouse for duplicates.
5. **Clock drift tolerance:** Server accepts events with timestamps up to ±5 minutes from server time (configurable).

## Batch Sizing

- **Recommended:** 50–100 events per batch.
- **Maximum:** 500 events per batch.
- **Minimum interval:** 60 seconds between batches (configurable).
- **Urgent flush:** Emergency events or buffer-full trigger immediate flush regardless of interval.

## References

- TZ v2.5 Table 15 (PoP event fields), §11.1 (PoP requirements), §24.8 (Normalized proof model)
- ADR-002 (Event bus — PoP ingest flow)
- ADR-003 (Device identity — signing)
