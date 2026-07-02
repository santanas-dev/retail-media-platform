# ADR-005: Monitoring and Observability

**Status:** Accepted
**Date:** 2026-07-02
**Phase:** 0 (Architecture Lock)
**Deciders:** Sergey Paschenko (project owner), Hermes Agent

## Context

ТЗ v2.5 §22.10 requires: structured logs, metrics, tracing, alerting across all backend services, Device Gateway, PoP ingestion, and analytics. The system must be observable for IT, security, and business stakeholders. Without an observability ADR, Phase 1 services will be built without knowing what telemetry to emit.

## Decision

**OpenTelemetry for tracing + Prometheus for metrics + structured JSON logs. Correlation IDs propagate across all services.**

### Correlation ID / Trace ID

Every request (user or device) generates or inherits a `correlation_id`:

```
User Browser                Control API              Orchestrator            NATS                Adapter
     │                          │                        │                    │                    │
     │ X-Correlation-ID: abc    │                        │                    │                    │
     ├─────────────────────────►│                        │                    │                    │
     │                          │ metadata.correlation_id: abc               │                    │
     │                          ├───────────────────────►│                    │                    │
     │                          │                        │ publish: cid=abc   │                    │
     │                          │                        ├───────────────────►│                    │
     │                          │                        │                    │ subscribe: cid=abc │
     │                          │                        │                    ├───────────────────►│
```

Rules:
- User requests: `X-Correlation-ID` header from client, or generated UUIDv4 if missing.
- Device requests: `X-Device-Correlation-ID` header on heartbeat/manifest/PoP.
- Service-to-service: propagate via NATS `metadata.correlation_id` envelope field.
- Log every correlation ID at entry and exit of each service handler.

### Structured Logging Format

All services emit JSON to stdout/stderr. Loki or ELK ingests from Docker logs.

```json
{
  "timestamp": "2026-07-02T08:00:00.123Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "service": "control-api|device-gateway|pop-ingestor|orchestrator-worker|adapter-kso|adapter-mock",
  "correlation_id": "uuid",
  "user_id": "uuid|null",
  "device_id": "uuid|null",
  "action": "campaign.create|manifest.generate|pop.ingest.batch|device.heartbeat|...",
  "message": "human-readable summary",
  "duration_ms": 42,
  "http": {
    "method": "GET|POST",
    "path": "/api/v1/campaigns",
    "status_code": 200,
    "client_ip": "10.x.x.x"
  },
  "error": {
    "code": "VALIDATION_ERROR|CONFLICT|RATE_LIMITED|...",
    "stack": "traceback (ERROR level only, sanitized: no secrets)"
  }
}
```

**Sanitization rules:**
- Never log: passwords, tokens, secrets, API keys, cookies, personal data, raw customer data.
- Mask sensitive fields: `password="***"`, `token="REDACTED"`, `signature="REDACTED"`.
- Truncate long strings to 1000 chars.

### Metric Groups

#### Control API Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rmp_http_requests_total` | Counter | method, path, status_code | Request count |
| `rmp_http_request_duration_ms` | Histogram | method, path | Latency p50/p95/p99 |
| `rmp_http_requests_in_flight` | Gauge | method, path | Concurrent requests |
| `rmp_auth_failures_total` | Counter | reason (invalid_creds/locked/mfa_failed) | Auth failures |
| `rmp_db_query_duration_ms` | Histogram | operation (select/insert/update) | DB latency |
| `rmp_rbac_denied_total` | Counter | permission, user_role | Permission denials |

#### Device Gateway Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rmp_devices_online` | Gauge | channel_type, device_type | Currently online devices |
| `rmp_device_heartbeat_total` | Counter | channel_type | Heartbeat count |
| `rmp_manifest_requests_total` | Counter | status (200/304/error) | Manifest pulls |
| `rmp_manifest_generation_duration_ms` | Histogram | channel_type | Manifest gen time |
| `rmp_device_session_establishments_total` | Counter | status | Session establishment |
| `rmp_device_auth_failures_total` | Counter | reason | Device auth failures |

#### PoP Ingestor Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rmp_pop_events_ingested_total` | Counter | channel_type, pop_mode | Events received |
| `rmp_pop_events_rejected_total` | Counter | reason (duplicate/signature/invalid) | Rejected events |
| `rmp_pop_batch_latency_ms` | Histogram | channel_type | End-to-end ingest time |
| `rmp_pop_ingest_lag_events` | Gauge | — | Queue backlog depth |

#### Orchestrator Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rmp_manifest_generation_total` | Counter | channel_type, status | Generated manifests |
| `rmp_manifest_targets_total` | Counter | channel_type | Total targets processed |
| `rmp_orchestrator_task_duration_ms` | Histogram | task_type | Task processing time |
| `rmp_rollout_progress` | Gauge | rollout_id | Rollout % complete |

#### Adapter Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rmp_adapter_tasks_total` | Counter | adapter, status | Tasks processed |
| `rmp_adapter_task_retry_total` | Counter | adapter | Retry count |
| `rmp_adapter_circuit_open` | Gauge | adapter | 1 if circuit breaker open |

#### Infrastructure Metrics (Standard)

- PostgreSQL: connections, query duration, replication lag.
- ClickHouse: inserts/sec, query duration, merge speed, disk usage.
- Redis: connected clients, memory, hit/miss ratio, evictions.
- MinIO: storage used, request rate, error rate.
- NATS: messages published/consumed, pending messages, consumer lag.

### Alert Categories

#### Critical (P1 — immediate response)

| Alert | Condition | For |
|-------|-----------|-----|
| Device gateway down | `up{service="device-gateway"} == 0` | 1 min |
| Massive device offline | `rmp_devices_online` drops >20% | 5 min |
| PoP ingestion stopped | `rate(rmp_pop_events_ingested_total[5m]) == 0` | 5 min |
| Emergency delivery failure | `rmp_emergency_delivery_failed > 0` | 0 min |
| Database connection exhausted | `pg_stat_activity > 80% max_connections` | 1 min |
| Disk full | `disk_used_percent > 90%` | 5 min |

#### Warning (P2 — investigate within 1 hour)

| Alert | Condition | For |
|-------|-----------|-----|
| Elevated error rate | `rate(rmp_http_requests_total{status_code=~"5.."}[5m]) > 1/s` | 10 min |
| ClickHouse ingestion lag | `rmp_pop_ingest_lag_events > 10000` | 10 min |
| Manifest generation slow | `p95(rmp_manifest_generation_duration_ms) > 5000` | 10 min |
| Redis memory high | `redis_memory_used_bytes > 80% max` | 10 min |
| Certificate expiring | `device_certificate_expiry_days < 30` | 24h |

#### Info (P3 — dashboard review)

| Alert | Condition | For |
|-------|-----------|-----|
| Adapter retry spike | `rate(rmp_adapter_task_retry_total[1h]) > 10` | 1h |
| Campaign SLA risk | Campaign actual < 90% of plan | end of day |

### Dashboards

| Dashboard | Audience | Key Panels |
|-----------|----------|------------|
| **Technical** | IT/Ops | Service health, error rates, latency, DB/Redis/ClickHouse status, disk |
| **Business** | Managers | Active campaigns, impressions today, plan/fact %, revenue, sold out |
| **Security** | InfoSec | Auth failures, permission denials, device revocations, MFA events |
| **Device Health** | Ops/Support | Online/offline by channel, error distribution, manifest version spread, stale devices |

### Privacy and Security

- **No secrets in logs/metrics:** passwords, tokens, API keys, certificates are REDACTED.
- **No raw customer data:** PII, advertiser contact details, contract values are replaced with `<REDACTED>` or aggregated.
- **Correlation IDs are UUIDv4:** carry no user or device identifying information directly.
- **Metric retention:** 30 days hot, 1 year cold. Log retention: 90 days hot, 180 days cold (TZ §22.11).
- **Access control:** Grafana behind AD/SSO with viewer/editor/admin roles.

## Consequences

- **Positive:** Unified telemetry across ~7 services; operational visibility from Day 1; alert rules prevent silent failures.
- **Negative:** Additional infrastructure (Prometheus, Grafana, Loki) in Docker Compose; OpenTelemetry adds slight overhead.
- **Risk:** If corporate observability stack (e.g., Datadog, Dynatrace) is mandated, OTEL exporters can be swapped without changing instrumentation code.

## References

- TZ v2.5 §22.10 (Observability: logs, metrics, tracing, alerts)
- TZ v2.5 §22.11 (Data Governance and retention)
- TZ v2.5 §14 (Security — no secrets in logs)
- ADR-002 (Event bus — correlation IDs in NATS envelopes)
