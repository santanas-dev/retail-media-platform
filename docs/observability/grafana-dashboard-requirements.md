# Grafana Dashboard Requirements — Retail Media Platform

**Version:** 1.0 | **Date:** 2026-07-01

> Requirements document. Dashboards to be created in Grafana.  
> No real hostnames or secrets.

---

## Dashboard 1: Backend Health Overview

**Purpose:** Quick health status of all backend components.

**Panels:**

| Panel | Type | Data Source | Query |
|---|---|---|---|
| Backend Liveness | Stat | Prometheus | `up{service="backend", check="liveness"}` |
| Backend Readiness | Stat | Prometheus | `up{service="backend", check="readiness"}` |
| Portal Health | Stat | Prometheus | `up{service="portal"}` |
| PostgreSQL Status | Stat | Prometheus | `health_dependency_failed{name="postgresql"}` |
| Redis Status | Stat | Prometheus | `health_dependency_unknown{name="redis"}` |
| MinIO Status | Stat | Prometheus | `health_dependency_unknown{name="minio"}` |
| Correlation ID present | Table | — | Last 10 requests |
| Uptime | Stat | Prometheus | `time() - min(up{service="backend"})` |

---

## Dashboard 2: Request Metrics

**Purpose:** API traffic and error patterns.

**Panels:**

| Panel | Type | Query |
|---|---|---|
| Request Rate | Graph | `rate(http_requests_total[5m])` |
| Error Rate | Graph | `rate(http_errors_total[5m])` |
| 5xx Rate | Graph | `rate(http_requests_total{status=~"5.."}[5m])` |
| 4xx Rate | Graph | `rate(http_requests_total{status=~"4.."}[5m])` |
| Latency p50 | Graph | `histogram_quantile(0.50, ...)` |
| Latency p95 | Graph | `histogram_quantile(0.95, ...)` |
| Latency p99 | Graph | `histogram_quantile(0.99, ...)` |
| Top endpoints by errors | Table | `topk(10, rate(http_errors_total[5m]))` |

---

## Dashboard 3: Gateway Heartbeat

**Purpose:** Device connectivity health.

**Panels:**

| Panel | Type | Query |
|---|---|---|
| Devices Online | Stat | `count(device_heartbeat_ok)` |
| Devices Missing (>5 min) | Stat | `count(device_heartbeat_missing_seconds > 300)` |
| Heartbeat Rate | Graph | `rate(device_heartbeats_total[5m])` |
| Device List | Table | Last heartbeat per device |

---

## Dashboard 4: Proof of Play

**Purpose:** PoP ingestion and campaign delivery.

**Panels:**

| Panel | Type | Query |
|---|---|---|
| PoP Events / sec | Graph | `rate(pop_events_total[1m])` |
| PoP Events (total today) | Stat | `increase(pop_events_total[24h])` |
| Delivery rate by campaign | Table | `topk(10, rate(delivery_events_total[5m]) by (campaign_id))` |
| Delivery rate by device | Table | `topk(10, rate(delivery_events_total[5m]) by (device_code))` |

---

## Dashboard 5: Emergency & Rate Limiter

**Purpose:** Security and emergency monitoring.

**Panels:**

| Panel | Type | Query |
|---|---|---|
| Rate Limit 429 Rate | Graph | `rate(http_429_total[5m])` |
| Rate Limit Remaining (emergency) | Gauge | last non-zero value |
| Last Emergency Dry-Run | Stat | Timestamp of last emergency preview |
| Emergency Capabilities | Table | Static info |

---

## Deployment

- [ ] Import dashboards into Grafana
- [ ] Set data source to Prometheus
- [ ] Set refresh interval: 30s
- [ ] Set time range: last 6 hours (default)
- [ ] Share with ops team
