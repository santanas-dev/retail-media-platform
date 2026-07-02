# Phase 1 — Rewrite Skeleton

**Date:** 2026-07-02
**Phase:** 1 (New Skeleton)
**Commit:** (to be committed)
**Previous:** Phase 0 (Architecture Lock)

## Purpose

Phase 1 creates the physical project structure defined in the Phase 0 architecture lock. All services are stubs — no business logic, no database schemas, no authentication. The goal is a compilable, startable project skeleton that validates the deployment model and service boundaries.

## What Exists

### Services

| Service | Entrypoint | Port | Type | Health |
|---------|-----------|------|------|--------|
| `control-api` | `apps/control-api/main.py` | 8000 | FastAPI | `/health/live`, `/health/ready` |
| `device-gateway` | `apps/device-gateway/main.py` | 8001 | FastAPI | `/health/live`, `/health/ready` |
| `pop-ingestor` | `apps/pop-ingestor/main.py` | 8002 | Async worker + HTTP health | `/health/live`, `/health/ready` |
| `orchestrator-worker` | `apps/orchestrator-worker/main.py` | 8003 | Async worker + HTTP health | `/health/live`, `/health/ready` |
| `mock-adapter` | `apps/adapter-workers/mock/main.py` | 8100 | Async worker + HTTP health | `/health/live`, `/health/ready` |

All services:
- Emit structured JSON logs to stdout
- Propagate `X-Correlation-ID` header
- Have `/health/live` (is the process alive?) and `/health/ready` (can it serve? — always "ok" in Phase 1, will check real dependencies later)
- No database connections, no authentication, no business logic

### Shared Packages

| Package | Path | Contents |
|---------|------|----------|
| `packages/domain/` | `__init__.py` | Shared enums: ChannelType, DeviceStatus, ProofMode, CampaignStatus, etc. |
| `packages/observability/` | `__init__.py` | Correlation ID helper, JSON logger, FastAPI request-logging middleware |
| `packages/contracts/` | `manifest_v1.schema.json`, `proof_event_v1.schema.json`, `README.md` | JSON Schema placeholders for manifest and proof events |

### Frontend

| App | Path | Stack | Status |
|-----|------|-------|--------|
| `admin-web` | `apps/admin-web/` | React 19 + TypeScript + Vite | Minimal app shell; no business pages |

### Infrastructure

| File | Purpose |
|------|---------|
| `infra/compose/docker-compose.phase1.yml` | Starts all 5 services + PostgreSQL, ClickHouse, Redis, NATS, MinIO with healthchecks |
| `infra/compose/Dockerfile.service` | Shared Dockerfile for Python service entrypoints |

## What Is Intentionally NOT Implemented

| Capability | Why Deferred | Target Phase |
|-----------|-------------|--------------|
| Database migrations (Alembic) | Schema comes in Phase 2 (Enterprise Foundation) | Phase 2 |
| User authentication (AD/SSO) | Identity domain is Phase 2 | Phase 2 |
| RBAC/RLS permission catalog | Phase 2 | Phase 2 |
| Device onboarding + JWT | Phase 3 (KSO Pilot Path) | Phase 3 |
| Manifest generation | Phase 3 (Orchestrator) | Phase 3 |
| PoP ingest pipeline (NATS → ClickHouse) | Phase 4 (Proof and Analytics) | Phase 4 |
| Adapter business logic (KSO, Android, etc.) | Phase 3-5 | Phase 3+ |
| Admin Web business pages | Phase 5 (Production Readiness) | Phase 5 |
| Monitoring dashboards (Prometheus/Grafana) | Phase 5 | Phase 5 |
| Load testing | Phase 5 | Phase 5 |
| Feature flags | Phase 2 | Phase 2 |
| CI/CD pipeline | Phase 1.1 (next sub-step) | Phase 1.1 |

## How To Verify

### Quick: Local Quality Gates

```bash
# Run all Phase 1 checks locally
bash scripts/ci/phase1-checks.sh
```

Checks included:
- Python syntax (`py_compile`) for all 7 Phase 1 Python files
- Python import smoke (modules import without errors)
- JSON Schema validation (valid JSON + required fields)
- Docker Compose config validation (syntax + required services)
- Frontend TypeScript type-check (`tsc --noEmit`) + build (`vite build`)

### Full: Docker Integration Test

```bash
# Start all infrastructure + services
docker compose -f infra/compose/docker-compose.phase1.yml up -d

# Check all services are healthy
docker compose -f infra/compose/docker-compose.phase1.yml ps

# Test individual health endpoints
curl http://localhost:8000/health/live   # control-api
curl http://localhost:8001/health/live   # device-gateway
curl http://localhost:8002/health/live   # pop-ingestor
curl http://localhost:8003/health/live   # orchestrator-worker
curl http://localhost:8100/health/live   # mock-adapter

# Stop everything
docker compose -f infra/compose/docker-compose.phase1.yml down -v
```

## What Was NOT Touched

- `backend/` — existing backend code untouched
- `apps/portal-web/` — existing Jinja portal untouched
- `apps/kso_player/`, `apps/kso_sidecar_agent/`, `apps/kso_state_adapter/` — untouched
- `docs/` — only this file added, no existing docs modified
- `.env`, `.gitignore`, `AGENTS.md` — untouched

## Next Steps

1. **Phase 1.1** — CI/CD pipeline: lint, type-check, test, build
2. **Phase 2** — Enterprise Foundation: migrations, identity, RBAC, org hierarchy, channels
