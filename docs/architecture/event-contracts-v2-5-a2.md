# Event Contracts v2.5 — A.2

> **Дата:** 2026-06-29 | **Этап:** A.2  
> **Основание:** ТЗ v2.5 Tables 32-33  
> **Статус:** ПРОЕКТ

---

## 1. Publication Flow

### publish.requested
```
Producer: Campaign Service
Consumer: Channel Orchestrator
Routing: orchestrator.tasks
```
```json
{
  "event_id": "uuid",
  "event_type": "publish.requested",
  "version": "1.0",
  "placement_code": "PL-2026-001",
  "campaign_code": "CMP-2026-001",
  "requested_by": "username",
  "idempotency_key": "pub-request-uuid",
  "timestamp": "2026-06-29T10:00:00Z"
}
```
**Retry:** 3x, backoff 5s  
**DLQ:** after 3 retries → ops alert

### manifest.generated
```
Producer: Channel Orchestrator
Consumer: Adapter Router
Routing: adapter.tasks.{channel_code}
```
```json
{
  "event_id": "uuid",
  "event_type": "manifest.generated",
  "version": "1.0",
  "manifest_code": "MF-2026-001",
  "placement_code": "PL-2026-001",
  "channel_code": "KSO",
  "manifest_schema_version": "1.0",
  "valid_from": "2026-07-01T00:00:00+03:00",
  "valid_to": "2026-07-14T23:59:59+03:00",
  "target_count": 500,
  "signature": "hmac-sha256:...",
  "timestamp": "..."
}
```

### channel.task.created
```
Producer: Orchestrator
Consumer: Channel Adapter (KSO/Android/ESL/LED)
Routing: adapter.tasks.{channel_code}.{adapter_id}
```
```json
{
  "event_id": "uuid",
  "task_id": "uuid",
  "channel_code": "KSO",
  "adapter_id": "kso-adapter-01",
  "manifest": { /* full manifest */ },
  "adapter_payload": { /* channel-specific */ },
  "target_devices": ["device-ext-code-1", "device-ext-code-2"],
  "priority": 50,
  "retry_policy": {"max_attempts": 3, "backoff_seconds": 10}
}
```

### adapter.delivery.attempted
```
Producer: Channel Adapter
Consumer: Orchestrator / Analytics
Routing: delivery.events
```
```json
{
  "event_id": "uuid",
  "event_type": "adapter.delivery.attempted",
  "task_id": "uuid",
  "adapter_id": "kso-adapter-01",
  "device_external_code": "KSO-003",
  "result": "delivered|failed|timeout",
  "error_code": "CONNECTION_REFUSED",
  "attempt_number": 1,
  "timestamp": "..."
}
```

### device.apply.ack
```
Producer: Device Gateway (from device)
Consumer: Orchestrator → Analytics
Routing: apply.ack.events → ClickHouse
```
```json
{
  "event_id": "uuid",
  "event_type": "device.apply.ack",
  "device_id": "uuid",
  "manifest_code": "MF-2026-001",
  "ack_type": "applied|error|rejected",
  "error_code": "INSUFFICIENT_SPACE",
  "applied_at": "2026-07-01T00:05:00Z",
  "device_signature": "hmac:...",
  "idempotency_key": "apply-ack-uuid"
}
```

### proof.received
```
Producer: PoP Ingestion (from device batch)
Consumer: Analytics → ClickHouse
Routing: proof.events.{channel_code}
```
```json
{
  "event_id": "uuid",
  "event_type": "proof.received",
  "batch_key": "batch-uuid",
  "events": [{
    "event_code": "pop-uuid-1",
    "proof_type": "real_playback",
    "device_id": "uuid",
    "campaign_code": "CMP-001",
    "placement_code": "PL-001",
    "creative_code": "CR-001",
    "rendition_code": "RND-001",
    "manifest_code": "MF-001",
    "started_at": "...",
    "duration_ms": 10000,
    "media_sha256": "abc123...",
    "playback_result": "success",
    "device_signature": "hmac:..."
  }],
  "timestamp": "..."
}
```

---

## 2. Operations Events

### rollout.paused / rollback.started
```
Producer: Operations Service
Consumer: Channel Orchestrator
Routing: operations.events
```
```json
{
  "event_id": "uuid",
  "event_type": "rollout.paused",
  "rollout_plan_code": "RL-001",
  "paused_at_step": 3,
  "error_rate": 0.15,
  "threshold": 0.10,
  "auto_triggered": true,
  "timestamp": "..."
}
```

### emergency.requested / applied / failed
```
Producer: Emergency Service
Consumer: Channel Orchestrator → Adapters
Routing: emergency.events (HIGH PRIORITY)
```
```json
{
  "event_id": "uuid",
  "event_type": "emergency.requested",
  "emergency_code": "EM-001",
  "action": "stop_ads",
  "level": "store",
  "level_ref": "STORE-042",
  "message_text": "Технические работы",
  "requested_by": "admin",
  "reason": "Плановая профилактика",
  "timestamp": "..."
}
```

---

## 3. Telemetry Events → ClickHouse

### device.heartbeat.received
```json
{
  "device_id": "uuid",
  "store_id": "uuid",
  "status": "online",
  "cpu_percent": 23.5,
  "memory_mb": 512,
  "disk_free_mb": 2048,
  "cache_size_mb": 350,
  "player_version": "1.2.3",
  "manifest_applied": "MF-2026-001",
  "error_count": 0,
  "received_at": "..."
}
```

### device.error.received
```json
{
  "device_id": "uuid",
  "error_code": "MANIFEST_SIGNATURE_INVALID",
  "message": "Manifest signature verification failed",
  "manifest_code": "MF-2026-001",
  "stack_trace": "...",
  "received_at": "..."
}
```

---

## 4. Security Requirements (все события)

| Требование | Применение |
|---|---|
| Подпись | HMAC (v1) / Ed25519 (production) |
| Idempotency | event_id / batch_key уникален |
| Проверка device | Сертификат/JWT device token |
| Несекретные поля | Никаких токенов/паролей в payload |
| Correlation ID | trace_id передаётся через всю цепочку |
| Timestamps | Всегда UTC |
| Retry + DLQ | Для всех критичных событий |

---

## 5. Event → ClickHouse Mapping

| Event | ClickHouse Table | Partition Key |
|---|---|---|
| proof.received | proof_events | toDate(received_at) |
| device.apply.ack | apply_ack_events | toDate(received_at) |
| adapter.delivery.attempted | delivery_events | toDate(timestamp) |
| device.heartbeat.received | device_telemetry | toDate(received_at) |
| device.error.received | device_telemetry (errors) | toDate(received_at) |

TTL: 12-18 месяцев горячее, 3-5 лет архив.
