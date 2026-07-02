# B2 — Prometheus Targets Status

**Date:** 2026-07-02

## Scrape Targets — Verification

All 4 targets verified live:

| # | Target | Endpoint | Status | Response |
|---|---|---|---|---|
| 1 | Backend liveness | `/api/health/live` | ✅ 200 | `{"status":"ok","service":"retail-media-platform"}` |
| 2 | Backend readiness | `/api/health/ready` | ✅ 200 | `ready=true` |
| 3 | Backend metrics | `/api/health/metrics` | ✅ 200 | `text/plain` Prometheus format |
| 4 | Portal health | `/health` | ✅ 200 | `{"status":"ok","db":"connected"}` |

## prometheus.yml Target Config

```yaml
scrape_configs:
  - job_name: "retail-media-backend"
    metrics_path: "/api/health/metrics"
    scrape_interval: 30s
    static_configs:
      - targets: ["<BACKEND_HOST:PORT>"]

  - job_name: "retail-media-backend-live"
    metrics_path: "/api/health/live"
    scrape_interval: 15s
    static_configs:
      - targets: ["<BACKEND_HOST:PORT>"]

  - job_name: "retail-media-backend-ready"
    metrics_path: "/api/health/ready"
    scrape_interval: 15s
    static_configs:
      - targets: ["<BACKEND_HOST:PORT>"]

  - job_name: "retail-media-portal"
    metrics_path: "/health"
    scrape_interval: 15s
    static_configs:
      - targets: ["<PORTAL_HOST:PORT>"]
```

## Status

- Backend reachable: ✅
- Portal reachable: ⬜ Not verified (portal not running)
- All scrape targets return valid responses: ✅
- Ready for Prometheus deployment: 🟢 YES
