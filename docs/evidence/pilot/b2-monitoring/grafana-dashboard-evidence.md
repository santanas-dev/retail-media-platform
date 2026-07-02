# B2 — Grafana Dashboard Evidence

**Date:** 2026-07-02 | **Status:** ⬜ NOT DEPLOYED — specs ready

## Dashboard Specifications

5 dashboards documented in `docs/observability/grafana-dashboard-requirements.md`:

| # | Dashboard | Panels | Ready |
|---|---|---|---|
| 1 | Backend Health Overview | 8 panels (liveness, readiness, PostgreSQL, Redis, MinIO, portal, correlation ID, uptime) | ✅ |
| 2 | Request Metrics | 8 panels (request rate, errors, 5xx, 4xx, p50/p95/p99, top endpoints) | ✅ |
| 3 | Gateway Heartbeat | 4 panels (online, missing, rate, device list) | ✅ |
| 4 | Proof of Play | 4 panels (PoP rate, total, by campaign, by device) | ✅ |
| 5 | Emergency & Rate Limiter | 4 panels (429 rate, RL remaining, last dry-run, capabilities) | ✅ |

## Deployment Steps

1. Start Grafana: `docker run -d -p 3000:3000 grafana/grafana`
2. Configure Prometheus data source
3. Import/create dashboards per spec
4. Set refresh: 30s, time range: last 6 hours

## Status

- Specs: ✅ Ready
- Grafana deployed: ⬜ Pending
- Dashboards created: ⬜ Pending
