# Event Contracts v1 — Retail Media Platform

**Version:** 1.0
**Phase:** 0 (Architecture Lock)
**Source:** ТЗ v2.5 §11, §24.8, §24.9; ADR-002

---

## Event Types

### 1. PoP Batch Ingest

**Subject:** `pop.ingest.batch`
**Publisher:** Device Gateway
**Consumer:** PoP Ingestor → ClickHouse
**Delivery:** JetStream (persisted, at-least-once, idempotent by `event_id`)

```json
{
  "batch_id": "uuid",
  "device_id": "uuid",
  "device_code": "KSO-003",
  "store_id": "uuid",
  "channel_type": "KSO",
  "device_type": "KSO_V1",
  "events": [
    {
      "event_id": "uuid",
      "campaign_id": "uuid",
      "campaign_code": "CAMP-2026-001",
      "placement_id": "uuid",
      "creative_version_id": "uuid",
      "media_asset_id": "uuid",
      "manifest_id": "uuid",
      "surface_id": "uuid (optional)",
      "started_at": "2026-07-02T08:00:00Z",
      "ended_at": "2026-07-02T08:00:10Z",
      "duration_ms": 10000,
      "media_sha256": "abc123...",
      "playback_result": "success|skipped|failed|interrupted",
      "failure_reason": "offline|missing_file|sha256_mismatch|manifest_expired|error|hidden_by_touch",
      "pop_mode": "real_playback|screen_render|idle_screen|template_applied|gateway_ack|label_ack|controller_ack",
      "device_signature": "Ed25519 or HMAC signature"
    }
  ],
  "batch_sequence": 142,
  "timestamp": "2026-07-02T08:01:00Z",
  "correlation_id": "uuid"
}
```

**Ack (response):**

```json
{
  "status": "accepted|partial",
  "accepted_count": 15,
  "rejected_count": 2,
  "rejected_event_ids": ["uuid1", "uuid2"],
  "rejection_reasons": {
    "uuid1": "duplicate_event_id",
    "uuid2": "invalid_signature"
  }
}
```

---

### 2. Device Heartbeat

**Subject:** `device.heartbeat`
**Publisher:** Device Gateway
**Consumer:** Analytics, Monitoring
**Delivery:** Core NATS (ephemeral, fire-and-forget)

```json
{
  "device_id": "uuid",
  "device_code": "KSO-003",
  "store_id": "uuid",
  "channel_type": "KSO",
  "timestamp": "2026-07-02T08:00:30Z",
  "player_version": "2.1.0",
  "chromium_version": "120.0.6099",
  "status": "online|degraded|error",
  "current_manifest_id": "uuid|null",
  "cache_size_bytes": 524288000,
  "cache_free_bytes": 387654321,
  "uptime_seconds": 86400,
  "last_error_code": "string|null",
  "ip_address": "10.x.x.x",
  "correlation_id": "uuid"
}
```

---

### 3. Manifest Generate Request

**Subject:** `manifest.generate.request`
**Publisher:** Control API (after approval + publish)
**Consumer:** Orchestrator Worker
**Delivery:** JetStream (persisted, exactly-once via dedup key)

```json
{
  "request_id": "uuid",
  "trigger": "campaign_publish|campaign_update|emergency|rollout|manual",
  "scope_type": "branch|cluster|store|device_group",
  "scope_id": "uuid",
  "placement_ids": ["uuid1", "uuid2"],
  "campaign_codes": ["CAMP-2026-001"],
  "priority": "normal|high|emergency",
  "requested_by": "uuid (user)",
  "correlation_id": "uuid",
  "timestamp": "2026-07-02T08:00:00Z"
}
```

---

### 4. Manifest Generated

**Subject:** `manifest.generated`
**Publisher:** Orchestrator Worker
**Consumer:** Device Gateway (for caching/invalidation)
**Delivery:** JetStream (persisted)

**Delivery semantics:** One event per manifest. The manifest targets one `device_id`. Surface-level targeting is INSIDE the manifest payload (`display_surfaces[]` array), not as separate events or device lists. This event notifies the Device Gateway that a new manifest version is available for caching/pre-fetch. The actual manifest content is served via `GET /device/v1/manifest`. The `surface_ids` field here is informational for analytics correlation, not a delivery target list.

```json
{
  "manifest_id": "uuid",
  "device_ids": ["uuid1", "uuid2", "..."],
  "surface_ids": ["uuid1", "uuid2", "..."],
  "total_targets": 42,
  "channel_type": "KSO",
  "manifest_version": 3,
  "valid_from": "2026-07-02T08:05:00Z",
  "valid_to": "2026-07-09T08:05:00Z",
  "signature_alg": "Ed25519",
  "generated_at": "2026-07-02T08:00:05Z",
  "request_id": "uuid",
  "correlation_id": "uuid"
}
```

---

### 5. Adapter Task (KSO)

**Subject:** `adapter.kso.task`
**Publisher:** Orchestrator Worker
**Consumer:** KSO Adapter Worker
**Delivery:** JetStream (persisted, queue group for load balancing)

```json
{
  "task_id": "uuid",
  "task_type": "manifest_deliver|media_precache|emergency_command|rollback",
  "device_ids": ["uuid1", "uuid2"],
  "surface_ids": ["uuid1"],
  "manifest_id": "uuid (optional)",
  "adapter_payload": {
    "display_mode": "portrait_overlay",
    "overlay_zone": {"x": 0, "y": 400, "w": 768, "h": 240},
    "hide_on_touch": true,
    "hide_timeout_sec": 30,
    "fallback_behavior": "show_filler"
  },
  "priority": "normal|high|emergency",
  "retry_policy": {
    "max_attempts": 5,
    "backoff_sec": [10, 30, 60, 300, 900]
  },
  "correlation_id": "uuid",
  "timestamp": "2026-07-02T08:00:06Z"
}
```

---

### 6. Adapter Result (KSO)

**Subject:** `adapter.kso.result`
**Publisher:** KSO Adapter Worker
**Consumer:** Orchestrator Worker (for rollout tracking)
**Delivery:** JetStream (persisted)

```json
{
  "task_id": "uuid",
  "status": "completed|partial|failed",
  "devices_ok": 40,
  "devices_failed": 2,
  "details": [
    {
      "device_id": "uuid",
      "device_code": "KSO-001",
      "status": "completed",
      "applied_at": "2026-07-02T08:00:15Z"
    },
    {
      "device_id": "uuid",
      "device_code": "KSO-002",
      "status": "failed",
      "error": "insufficient_disk_space",
      "error_message": "Cache full: 500MB/500MB, need 50MB free"
    }
  ],
  "correlation_id": "uuid",
  "completed_at": "2026-07-02T08:00:20Z"
}
```

---

### 7. Emergency Execute

**Subject:** `emergency.execute`
**Publisher:** Control API
**Consumer:** Orchestrator Worker (high priority)
**Delivery:** JetStream (persisted, high priority)

```json
{
  "emergency_id": "uuid",
  "action_type": "stop_all|replace_with_message|fallback|resume",
  "message": "Технические работы. Реклама временно не показывается.",
  "scope_type": "network|branch|cluster|store",
  "scope_id": "uuid (optional)",
  "priority": "emergency",
  "requested_by": "uuid",
  "reason": "Сбой кассового ПО в филиале",
  "correlation_id": "uuid",
  "timestamp": "2026-07-02T08:00:00Z"
}
```

---

### 8. Device Apply Ack

**Subject:** `device.apply.ack`
**Publisher:** Device Gateway (from device)
**Consumer:** Orchestrator Worker, Analytics
**Delivery:** JetStream (persisted)

```json
{
  "device_id": "uuid",
  "device_code": "KSO-003",
  "manifest_id": "uuid",
  "manifest_version": 3,
  "status": "applied|error|not_supported|insufficient_space|signature_invalid",
  "error_message": "string|null",
  "applied_at": "2026-07-02T08:00:15Z",
  "correlation_id": "uuid"
}
```

---

### 9. Audit Event

**Subject:** `audit.event`
**Publisher:** All services
**Consumer:** Audit Logger → PostgreSQL
**Delivery:** JetStream (persisted)

```json
{
  "event_id": "uuid",
  "user_id": "uuid|null",
  "actor_role": "system_admin|ad_manager|approver|system|device",
  "action": "campaign.submit|campaign.approve|device.register|emergency.stop|user.create|...",
  "target_type": "campaign|user|device|manifest|approval|emergency",
  "target_ref": "CAMP-2026-001",
  "details": {
    "previous_status": "draft",
    "new_status": "pending_approval",
    "reason": "Campaign ready for review"
  },
  "ip_address": "10.x.x.x",
  "user_agent": "Mozilla/5.0 ...",
  "correlation_id": "uuid",
  "timestamp": "2026-07-02T08:00:00Z"
}
```

---

## Event Envelope (common wrapper)

All events published on NATS share a common envelope:

```json
{
  "metadata": {
    "event_id": "uuid",
    "event_type": "pop.ingest.batch|device.heartbeat|manifest.generate.request|...",
    "version": "1.0",
    "timestamp": "2026-07-02T08:00:00Z",
    "correlation_id": "uuid",
    "source_service": "device-gateway|control-api|orchestrator-worker"
  },
  "payload": { ... }
}
```

## Delivery Guarantees

| Guarantee | Subjects | Mechanism |
|-----------|----------|-----------|
| **At-least-once** | `pop.ingest.batch`, `device.apply.ack`, `manifest.*`, `adapter.*`, `emergency.*`, `audit.*` | JetStream with ack |
| **Idempotent** | `pop.ingest.batch`, `manifest.generate.request` | Dedup key (event_id / request_id) |
| **Fire-and-forget** | `device.heartbeat` | Core NATS (no persistence) |
| **Ordered** | `pop.ingest.batch` per device | JetStream with partition key = device_id |

## References

- TZ v2.5 §11 (PoP requirements), §24.8 (Normalized proof model), §24.9 (Event-driven architecture)
- ADR-002 (Event bus — NATS JetStream baseline)
