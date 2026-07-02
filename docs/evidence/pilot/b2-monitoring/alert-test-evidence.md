# B2 — Alert Test Evidence

**Date:** 2026-07-02 | **Status:** ⬜ NOT TESTED — alert rules ready

## Alert Rules Template

9 alert rules in `docs/observability/alert-rules.example.yml`:

| # | Alert | Severity | For | Ready |
|---|---|---|---|---|
| A1 | BackendDown | critical | 1m | ✅ |
| A2 | ReadinessFailed | critical | 2m | ✅ |
| A3 | DatabaseDependencyFailed | critical | 1m | ✅ |
| A4 | API5xxSpike | high | 5m | ✅ |
| A5 | HeartbeatMissing | high | 5m | ✅ |
| A6 | HighErrorRate | high | 5m | ✅ |
| A7 | PoPDrop | medium | 10m | ✅ |
| A8 | RateLimitSpike | medium | 5m | ✅ |
| A9 | DependencyUnknown | low | 10m | ✅ |

## Test Alert Plan

1. Start Prometheus with alert rules loaded
2. Verify rules: `curl :9090/api/v1/rules`
3. Fire test alert: temporarily stop backend → BackendDown fires
4. Verify Alertmanager receives alert
5. Verify notification delivered to channel
6. Restore backend → alert resolves

## Status

- Alert rules spec: ✅ Ready
- Prometheus + Alertmanager: ⬜ Pending
- Test alert: ⬜ Pending
