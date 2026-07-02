# Universal Manifest v1 — Schema Specification

**Version:** 1.0
**Phase:** 0 (Architecture Lock)
**Source:** ТЗ v2.5 Table 13; §8.2, §24.7

---

## Purpose

The Universal Manifest is the canonical contract between the platform and every channel adapter. It contains a common part (identical for all devices) and a channel-specific `adapter_payload`.

**Delivery model:** One manifest is delivered to one gateway/physical device runtime. The manifest may reference one or many `display_surfaces` inside it. Inventory and reporting remain surface-based; delivery is device-based. A manifest with multiple surfaces targets all surfaces controlled by that device (e.g., ESL gateway with N labels, LED controller with N panels).

## Schema (v1.0)

```json
{
  "$schema": "https://rmp.internal/manifest/v1/schema.json",
  "manifest": {
    "manifest_id": "uuid",
    "manifest_version": 3,
    "schema_version": "1.0",
    "device_id": "uuid",
    "device_code": "KSO-003",
    "store_id": "uuid",
    "store_code": "ST-042",
    "channel_type": "KSO|ANDROID_TV|PRICE_CHECKER|ESL|LED",
    "device_type": "KSO_V1|ANDROID_TV_V1|PRICE_CHECKER_V1|ESL_GW_V1|LED_CTRL_V1",
    "display_surfaces": [
      {
        "surface_id": "uuid",
        "surface_code": "SURF-001"
      }
    ],
    "playlist_version": "2026-07-01-001",
    "valid_from": "2026-07-02T00:00:00Z",
    "valid_to": "2026-07-09T00:00:00Z",
    "offline_ttl_hours": 168,
    "generated_at": "2026-07-01T23:55:00Z",
    "priority": "normal|high|emergency",
    "emergency_flag": false,
    "capabilities": {
      "resolution": {"w": 1440, "h": 1080},
      "orientation": "landscape|portrait",
      "supported_formats": ["image/png", "image/jpeg", "video/mp4", "image/webp"],
      "max_file_size_bytes": 10485760,
      "max_duration_sec": 30,
      "supports_video": true,
      "supports_animation": false,
      "supports_interactive": false,
      "pop_mode": "real_playback",
      "display_zones": [
        {
          "zone_id": "ad_zone",
          "x": 0, "y": 0, "w": 1440, "h": 1080,
          "priority": 1
        }
      ]
    },
    "media_files": [
      {
        "media_id": "uuid",
        "creative_version_id": "uuid",
        "rendition_id": "uuid",
        "display_name": "Brand X Summer Ad v3",
        "mime_type": "image/png",
        "url": "https://minio.internal.rmp/bucket/renditions/abc123.png",
        "presigned_url": "https://minio.internal.rmp/bucket/renditions/abc123.png?X-Amz-...",
        "presigned_expires_at": "2026-07-03T00:00:00Z",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "size_bytes": 524288,
        "width": 1440,
        "height": 1080,
        "duration_sec": 10
      },
      {
        "media_id": "uuid",
        "creative_version_id": "uuid",
        "rendition_id": "uuid",
        "display_name": "Store Promo Q3",
        "mime_type": "video/mp4",
        "url": "https://minio.internal.rmp/bucket/renditions/def456.mp4",
        "presigned_url": "...",
        "presigned_expires_at": "2026-07-03T00:00:00Z",
        "sha256": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a",
        "size_bytes": 2048576,
        "width": 1440,
        "height": 1080,
        "duration_sec": 15
      }
    ],
    "playlist": [
      {
        "item_id": "uuid",
        "media_id": "uuid",
        "creative_version_id": "uuid",
        "order": 1,
        "duration_ms": 10000,
        "weight": 2,
        "priority": 50,
        "start_time": "08:00",
        "end_time": "12:00",
        "days_of_week": [1, 2, 3, 4, 5],
        "conditions": {
          "campaign_code": "CAMP-2026-001",
          "placement_id": "uuid"
        }
      }
    ],
    "fallback_rules": {
      "on_manifest_expired": "show_filler",
      "on_network_lost": "continue_last_valid",
      "on_insufficient_space": "show_filler",
      "filler_media_ids": ["uuid-filler-1", "uuid-filler-2"]
    },
    "adapter_payload": {
      "display_mode": "portrait_overlay",
      "overlay_zone": {"x": 0, "y": 400, "w": 768, "h": 240},
      "hide_on_touch": true,
      "hide_timeout_sec": 30,
      "chromium_args": ["--kiosk", "--no-first-run", "--disable-sync"],
      "screensaver_interval_sec": 600
    },
    "signature": {
      "algorithm": "Ed25519",
      "value": "base64-encoded-signature",
      "public_key_fingerprint": "SHA256:abc123..."
    }
  }
}
```

---

## Field-Level Description

| Path | Type | Required | Description |
|------|------|----------|-------------|
| `manifest.manifest_id` | UUID | Yes | Unique version identifier |
| `manifest.manifest_version` | int | Yes | Monotonically increasing version number |
| `manifest.schema_version` | string | Yes | Schema version for forward compat |
| `manifest.device_id` | UUID | Yes | Target physical device |
| `manifest.device_code` | string | Yes | Human-readable device code |
| `manifest.store_id` | UUID | Yes | Store where device is located |
| `manifest.store_code` | string | Yes | Human-readable store code |
| `manifest.channel_type` | enum | Yes | KSO, ANDROID_TV, PRICE_CHECKER, ESL, LED |
| `manifest.device_type` | enum | Yes | Specific device type code |
| `manifest.surface_id` | UUID | No | For multi-surface devices/esl/led |
| `manifest.playlist_version` | string | Yes | Logical playlist version label |
| `manifest.valid_from` | ISO 8601 | Yes | When manifest becomes active |
| `manifest.valid_to` | ISO 8601 | Yes | When manifest expires |
| `manifest.offline_ttl_hours` | int | Yes | How long device can run offline (7 days = 168h) |
| `manifest.priority` | enum | Yes | normal, high, emergency |
| `manifest.emergency_flag` | bool | Yes | True for emergency manifests |
| `manifest.capabilities` | object | Yes | Device capability profile at manifest generation time |
| `media_files[].url` | string | Yes | MinIO direct URL (internal network) |
| `media_files[].presigned_url` | string | Yes | Short-lived signed URL (external/VPN) |
| `media_files[].sha256` | string | Yes | SHA-256 hash — MUST be verified before play |
| `media_files[].duration_sec` | int | No | Duration in seconds (required for video) |
| `playlist[].order` | int | Yes | Playback order within the playlist |
| `playlist[].weight` | int | Yes | Relative weight for frequency scheduling |
| `playlist[].priority` | int | Yes | Priority level (higher = more important) |
| `playlist[].start_time` | string | No | Time-of-day constraint (HH:MM, local time) |
| `playlist[].days_of_week` | int[] | No | Day constraints (1=Mon, 7=Sun) |
| `fallback_rules.*` | object | Yes | Behavior when manifest/media is unavailable |
| `adapter_payload` | object | Yes | Channel-specific parameters |
| `signature.algorithm` | enum | Yes | Ed25519 (prod), HMAC-SHA256 (dev/mock) |
| `signature.value` | string | Yes | Base64-encoded signature over canonical JSON |

## Signature Rules

1. **Canonical form:** JSON keys sorted alphabetically, no whitespace, UTF-8.
2. **Signed payload:** The entire `manifest` object (excluding the `signature` field itself).
3. **Algorithm:** Ed25519 for production, HMAC-SHA256 acceptable for dev/mock.
4. **Verification:** Player MUST verify signature before applying manifest. Invalid signature → reject, report error, continue with last valid manifest.
5. **Key rotation:** Manifest includes `public_key_fingerprint` for key identification.

## Versioning & Compatibility

- **Schema version** in manifest allows forwards compatibility.
- **Backwards compatible:** Adding new optional fields is OK without schema version bump.
- **Breaking change:** Removing required fields, changing field types → new schema version + staged rollout.
- **Device negotiation:** Device reports supported `schema_versions` in heartbeat/capabilities. Server sends compatible version.

## Security Constraints

- JWT/access token MUST NOT appear in manifest URL fields.
- `presigned_url` MUST have short TTL (≤24h) and be regenerated on each manifest pull.
- `adapter_payload` MUST NOT contain secrets, internal hostnames, or database credentials.
- All media URLs MUST go through Device Gateway authorization, not direct MinIO access.

## Size Constraints

- Maximum manifest size: 1 MB (for 40 000 devices × 30s polling, bandwidth at ~3 GB/min).
- If a device's playlist exceeds this, split into separate manifests or paginate media_files.

## References

- TZ v2.5 Table 13 (Manifest fields), §8.2 (Manifest requirements), §24.7 (Universal manifest)
- ADR-003 (Device identity — no tokens in URLs)
- ERD v2.5 (manifest → physical_device FK, display_surfaces referenced inside manifest)
- Critical Review P0 fix: delivery is device-based, targeting is surface-based
