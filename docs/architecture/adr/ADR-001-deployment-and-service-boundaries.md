# ADR-001: Deployment Model and Service Boundaries

**Status:** Accepted
**Date:** 2026-07-02
**Phase:** 0 (Architecture Lock)
**Deciders:** Sergey Paschenko (project owner), Hermes Agent

## Context

ТЗ v2.5 §24.2 defines a modular runtime architecture with separated processes: Control Plane, Device Gateway, PoP Ingestion, Channel Orchestrator, Adapter Workers, Admin Web, Advertiser Web, KSO Sidecar, KSO Player. The system must scale from local development (Docker Compose) to production (40 000+ devices across 10 000 stores).

The `rmp_rewrite_starting_decisions.md` confirms Docker-first deployment with a staged path: local → pilot → test store → production.

## Decision

**Docker-first deployment with explicit service boundaries.**

### Runtime Services (from TZ §24.2)

```
┌──────────────────────────────────────────────────────┐
│                  Reverse Proxy / LB                    │
│               (nginx / HAProxy / Traefik)              │
└──────┬──────────┬──────────┬──────────┬───────────────┘
       │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────────┐
  │Control │ │Device  │ │PoP     │ │Orchestrator│
  │API     │ │Gateway │ │Ingestor│ │Worker      │
  │:8000   │ │:8001   │ │:8002   │ │:8003       │
  └────────┘ └────────┘ └───┬────┘ └───┬────────┘
                             │          │
  ┌──────────────────────────▼──────────▼──────────────┐
  │                  Event Bus (NATS JetStream)          │
  └──────┬──────────────────────────────────────────────┘
         │
  ┌──────▼──────────────────────────────────────┐
  │          Adapter Workers (one per channel)    │
  │  ┌──────┐ ┌───────────┐ ┌──────────┐        │
  │  │ mock │ │ kso       │ │ android  │  ...   │
  │  └──────┘ └───────────┘ └──────────┘        │
  └──────────────────────────────────────────────┘

  ┌────────────┐  ┌──────────────┐
  │ Admin Web  │  │ Advertiser   │
  │ React SPA  │  │ Web React    │
  │ :3000      │  │ :3001        │
  └────────────┘  └──────────────┘
```

### Staged Deployment Path

| Stage | Infrastructure | Acceptance |
|-------|---------------|------------|
| **Local** | `docker compose up` | All services, infra, migrations start clean |
| **Pilot** | 1 Docker host | Explicit backups, monitoring, restore drill |
| **Test Store** | ≥2 backend/gateway instances behind reverse proxy | HA posture verified |
| **Production** | Multiple Docker hosts / Swarm / approved orchestrator | HA PostgreSQL/ClickHouse/MinIO, backup proof, load tests at 40 000 devices |

### Service Boundaries

| Service | Network | Accesses Directly | Must NOT Access Directly |
|---------|---------|-------------------|--------------------------|
| **Control API** | Internal/VPN only | PostgreSQL, Redis, MinIO | ClickHouse (write), Device Gateway internal |
| **Device Gateway** | Corporate network, devices connect outbound | Redis (sessions), NATS (events), MinIO (media URLs) | PostgreSQL (except read-only via Control API), Admin endpoints |
| **PoP Ingestor** | Internal | NATS (consume), ClickHouse (write) | PostgreSQL, MinIO |
| **Orchestrator Worker** | Internal | PostgreSQL, NATS (publish tasks) | Device Gateway internal, ClickHouse |
| **Adapter Workers** | Internal | NATS (consume tasks, publish results), Control API | PostgreSQL, ClickHouse, MinIO DIRECTLY — use approved APIs/events |
| **Admin Web** | Internal/VPN | Control API | Device Gateway, PostgreSQL, ClickHouse directly |
| **Advertiser Web** | VPN or public with auth | Control API (read-only advertiser scope) | All other APIs |

### Infrastructure (Docker Compose)

| Service | Port (internal) | Notes |
|---------|-----------------|-------|
| PostgreSQL 16 | 5432 | Operational source of truth |
| ClickHouse | 8123/9000 | PoP, heartbeat, analytics |
| Redis | 6379 | Cache, sessions, rate limits, short-lived locks |
| MinIO | 9000 (API), 9001 (Console) | Versioned media, manifest packages, report artifacts |
| NATS JetStream | 4222 | Events, commands, inter-service messaging |

## Consequences

- **Positive:** Clear separation of blast radius; each service scales independently; adapter workers isolated per channel; Device Gateway and Control API cannot share failure modes.
- **Negative:** Initial complexity of 4+ runtime services instead of 1 monolith; need for event bus from Day 1.
- **Risk:** If Kubernetes/OpenShift is mandated later, service boundaries remain clean; only deployment manifests change.

## References

- TZ v2.5 §4.2 (Technology Stack), §4.3 (Network Placement), §24.2 (Target Architecture)
- `rmp_rewrite_starting_decisions.md` — Confirmed Decisions
- `rmp_enterprise_architecture_review.md` — Recommended Target Architecture
