# Monitoring Deployment Checklist

**Version:** 1.0 | **Date:** 2026-07-01 | **Owner:** Ops Team

> **SCOPE:** Lab/stage environment. Templates/configs only.  
> **STATUS:** ⬜ Not deployed — checklist + config templates ready.

---

## 1. Prerequisites

| # | Item | Status |
|---|---|---|
| 1.1 | Prometheus installed or Docker image available | ⬜ |
| 1.2 | Grafana installed or Docker image available | ⬜ |
| 1.3 | Network access to backend `/api/health/metrics` | ⬜ |
| 1.4 | Network access to backend `/api/health/live` | ⬜ |
| 1.5 | Network access to backend `/api/health/ready` | ⬜ |
| 1.6 | Alerting channel configured (email / Slack / Telegram) | ⬜ |

---

## 2. Prometheus Configuration

Use template: `docs/observability/prometheus.example.yml`

**Scrape targets:**

| Target | Endpoint | Interval | Labels |
|---|---|---|---|
| Backend health — liveness | `GET /api/health/live` | 15s | `service=backend` |
| Backend health — readiness | `GET /api/health/ready` | 15s | `service=backend` |
| Backend metrics | `GET /api/health/metrics` | 30s | `service=backend` |
| Portal health | `GET /health` | 15s | `service=portal` |

**Deployment steps:**
- [ ] Copy `prometheus.example.yml` → `prometheus.yml`
- [ ] Update `<BACKEND_HOST:PORT>` with actual values
- [ ] Start Prometheus: `docker run -d -p 9090:9090 -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus`
- [ ] Verify: `curl http://localhost:9090/api/v1/targets`
- [ ] Verify: `curl http://localhost:9090/api/v1/query?query=up`

---

## 3. Grafana Configuration

**Dashboards required:**

| Dashboard | Panels | Data Source |
|---|---|---|
| Backend Health | Liveness (up/down), Readiness (ok/degraded), Dependency status | Prometheus |
| Request Metrics | Request rate, Error rate, Latency (p50/p95/p99) | Prometheus |
| Gateway Heartbeat | Devices online, Heartbeat missing > 5 min | Prometheus |
| PoP Ingestion | PoP events/sec, PoP drop rate | Prometheus |
| Emergency Dry-Run | Last dry-run status, Capabilities | Prometheus |
| Rate Limiter | 429 rate, Rate limit remaining by endpoint | Prometheus |

**Deployment steps:**
- [ ] Start Grafana: `docker run -d -p 3000:3000 grafana/grafana`
- [ ] Configure Prometheus data source
- [ ] Import dashboards or create from `docs/observability/grafana-dashboard-requirements.md`
- [ ] Set default time range: last 6 hours
- [ ] Set refresh interval: 30s

---

## 4. Alert Rules

Use template: `docs/observability/alert-rules.example.yml`

**Required alerts:**

| # | Alert | Expression | Severity | Cooldown |
|---|---|---|---|---|
| A1 | Backend down | `up{service="backend"} == 0` for 1m | **Critical** | 5m |
| A2 | Readiness failed | `health_ready != 1` for 2m | **Critical** | 5m |
| A3 | API 5xx spike | `rate(http_requests_total{status=~"5.."}[5m]) > 10` | **High** | 10m |
| A4 | Heartbeat missing | Device heartbeat absent for > 5 min | **High** | 10m |
| A5 | PoP drop | `rate(pop_events_total[10m]) < 10` (below baseline) | **Medium** | 15m |
| A6 | DB dependency failed | `health_dependency_failed{name="postgresql"}` for 1m | **Critical** | 5m |
| A7 | Redis/MinIO unknown | `health_dependency_unknown` for 10m | **Low** | 30m |
| A8 | Rate limit spike | `rate(http_429_total[5m]) > 5` | **Medium** | 10m |
| A9 | High error rate | `rate(http_errors_total[5m]) > rate(http_requests_total[5m]) * 0.05` | **High** | 5m |

---

## 5. Escalation Path

| Level | Who | Channel | Response Time |
|---|---|---|---|
| **Critical** (A1, A2, A6) | Ops Lead → Dev Lead | Phone + Alert channel | < 5 min |
| **High** (A3, A4, A9) | Ops Team | Alert channel | < 15 min |
| **Medium** (A5, A8) | Ops Team | Alert channel | < 30 min |
| **Low** (A7) | Ops Team | Chat message | < 1 hour |

---

## 6. Evidence Requirements

| Artifact | Collected |
|---|---|
| Prometheus targets healthy | ⬜ |
| All 4 scrape targets returning 200 | ⬜ |
| Grafana dashboards visible | ⬜ |
| Alert rules loaded in Prometheus | ⬜ |
| Alertmanager configured | ⬜ |
| Test alert fired and acknowledged | ⬜ |
| Escalation contacts verified | ⬜ |

---

## 7. Decision

| Gate | Result |
|---|---|
| Monitoring deployed | ⬜ Yes / ⬜ No |
| Alerts configured and tested | ⬜ Yes / ⬜ No |
| Ready for pilot monitoring | ⬜ Yes / ⬜ No |
| Approver | ______________ | Date: __-__-__ |
