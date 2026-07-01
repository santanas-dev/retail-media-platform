# Monitoring & Alerting Requirements

**Date:** 2026-07-02 | **Phase:** H.2 target | **Owner:** Ops/Dev (TBD)

> **Status:** ❌ NOT IMPLEMENTED — requirements documented, implementation in H.2.

---

## 1. Metrics (Prometheus)

### API / Backend

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, endpoint, status | Total API requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | API latency |
| `http_errors_total` | Counter | endpoint, status_code | 4xx/5xx errors |
| `db_query_duration_seconds` | Histogram | operation | DB query time |

### Gateway

| Metric | Type | Labels | Description |
|---|---|---|---|
| `gateway_manifest_pulls_total` | Counter | device_code, channel | Manifest pulls |
| `gateway_heartbeat_total` | Counter | device_code | Heartbeats received |
| `gateway_heartbeat_freshness_seconds` | Gauge | device_code | Time since last heartbeat |
| `gateway_pop_events_total` | Counter | event_type, device_code | PoP events ingested |
| `gateway_media_downloads_total` | Counter | creative_code, status | Media downloads |
| `gateway_device_online_count` | Gauge | channel | Devices online |

### Infrastructure

| Metric | Type | Labels | Description |
|---|---|---|---|
| `pg_connections_active` | Gauge | — | Active DB connections |
| `pg_replication_lag_bytes` | Gauge | — | Replication lag |
| `redis_memory_used_bytes` | Gauge | — | Redis memory |
| `minio_objects_total` | Gauge | bucket | Objects in MinIO |
| `disk_usage_percent` | Gauge | mount | Disk usage |
| `cpu_usage_percent` | Gauge | container | CPU |
| `memory_usage_bytes` | Gauge | container | Memory |

### Emergency

| Metric | Type | Labels | Description |
|---|---|---|---|
| `emergency_api_calls_total` | Counter | endpoint | Emergency API calls |
| `emergency_errors_total` | Counter | endpoint | Emergency API errors |

---

## 2. Alerts (Alertmanager)

| Alert | Severity | Condition | For | Channel |
|---|---|---|---|---|
| GatewayDown | Critical | `gateway_up == 0` | 1m | Pager |
| High5xxRate | Critical | `http_5xx_rate > 5%` | 5m | Pager |
| PoPDrop | Warning | `gateway_pop_events_total drop > 50%` | 10m | Slack |
| HeartbeatMissing | Warning | `gateway_heartbeat_freshness > threshold` | 5m | Slack |
| DeviceOfflineSpike | Critical | `device_online_count drop > 20%` | 5m | Pager |
| DBUnavailable | Critical | `pg_up == 0` | 1m | Pager |
| RedisUnavailable | Warning | `redis_up == 0` | 1m | Slack |
| MinIOUnavailable | Warning | `minio_up == 0` | 1m | Slack |
| DiskSpaceLow | Warning | `disk_usage > 85%` | 5m | Slack |
| AuthFailuresSpike | Warning | `http_401_rate > 10%` | 5m | Slack |
| NoPoPFromPilot | Warning | `pilot_device_pop == 0 for 30m` | 10m | Slack |
| DeviceTokenIssue | Warning | `gateway_auth_failures > threshold` | 5m | Slack |
| MigrationFail | Critical | `alembic_current != alembic_head` | 1m | Pager |
| BackupFail | Critical | `backup_success == 0 for 24h` | 0 | Pager |

---

## 3. Observability Requirements

| Requirement | Status | Notes |
|---|---|---|
| Correlation ID (X-Request-ID) | ❌ Missing | Propagate through all services |
| Structured logs (JSON) | ⬜ Partial | Audit events only |
| Request ID in logs | ❌ Missing | Trace single request |
| Device code in logs | ❌ Missing | Trace device flow |
| Campaign/placement tracing (safe) | ❌ Missing | No secrets |
| No secrets in logs | ✅ Ready | Validators active |
| Log retention: 30 days | ❌ Missing | Configure rotation |

---

## 4. Dashboards (Grafana)

| Dashboard | Panels |
|---|---|
| **API Overview** | Request rate, latency p50/p95/p99, error rate, top endpoints |
| **Gateway Health** | Device online count, heartbeat freshness, manifest pulls, PoP rate |
| **Analytics** | PoP events by channel, delivery metrics, device health |
| **Infrastructure** | CPU/Memory/Disk, DB connections, Redis/MinIO |
| **Emergency** | API calls, preview/simulate rate |
| **Alerts** | Active alerts, alert history |

---

## 5. Logging Requirements

| Source | Format | Destination |
|---|---|---|
| Backend API | JSON | stdout → Loki/ELK |
| Portal | JSON | stdout → Loki/ELK |
| Device Gateway | JSON | stdout → Loki/ELK |
| PostgreSQL | CSV | pg logs |
| Redis | — | syslog |
| MinIO | JSON | stdout |

---

## 6. Health Check Requirements

| Endpoint | Checks |
|---|---|
| `GET /health` (backend) | DB connectivity, Redis ping |
| `GET /health` (portal) | Backend reachable |
| `GET /api/gateway/health` | DB, Redis, MinIO |

Current: basic `/health` exists ✅ but needs expansion.
