# RMP Rewrite: Starting Decisions

## Confirmed Decisions

These decisions are accepted as the baseline for the enterprise rewrite.

| Area | Decision |
|---|---|
| Deployment base | Docker-first. Use Docker Compose for local/dev/test/pilot. For production, design for multiple Docker hosts behind a load balancer, not a single flat server. |
| Event broker | No corporate broker is currently approved. Baseline recommendation: NATS JetStream in Docker, behind an internal event-bus abstraction. |
| Device identity | mTLS is not confirmed. Start with device onboarding code + device secret/certificate material + short-lived JWT session. Keep mTLS-ready interfaces. Never put tokens in URLs. |
| User identity | AD integration is required. Local users are only break-glass/admin fallback. |
| First pilot | One test KSO first, then one test store. No fleet rollout before physical proof. |
| Frontend | React + TypeScript is approved for the rewrite. Current Jinja portal is reference/prototype only. |
| Master data | Price/SKU/store/check master integrations are not blocking the architecture start. Use import/adapter contracts and synthetic data first. |
| Advertiser PDF legal status | Not legally significant. It is a business report with system stamp, immutable snapshot, audit trail, and export history. |

## Critical Interpretation

Docker is acceptable as the deployment technology, but a single Docker Compose
server is not an enterprise production architecture for 40 000+ devices. The
project should still be Docker-first, with a staged path:

1. Local development: Docker Compose.
2. Pilot: one Docker host, explicit backups, monitoring and restore drill.
3. Test store: at least two backend/device-gateway instances behind reverse proxy.
4. Production: multiple Docker hosts or Docker Swarm/approved equivalent, HA
   PostgreSQL/ClickHouse/MinIO strategy, backup/restore proof and load tests.

If Kubernetes/OpenShift is not available, do not block the project. Design the
services so they can run as Docker containers with explicit ports, health checks,
volumes, logs and environment contracts.

## Recommended Baseline Stack

Backend/services:

- Python 3.12+
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic v2
- NATS JetStream for events and commands
- PostgreSQL for operational data
- ClickHouse for PoP, heartbeat, proof and analytical events
- Redis for cache, rate limits, short-lived locks and web sessions
- MinIO for media, manifest packages and report artifacts

Frontend:

- React
- TypeScript
- Vite
- TanStack Router or React Router
- TanStack Query
- A restrained internal design system, not a marketing UI

Device/runtime:

- KSO sidecar and Chromium player as first production channel
- Device manifest pull with ETag/304 and jitter
- Local cache, offline TTL and fallback
- PoP batch buffer and resend

Security:

- AD/SSO for users
- MFA policy for critical roles, if exposed by AD/IdP
- break-glass local admin only
- device code onboarding + rotated secret/certificate material
- short-lived device access tokens
- Ed25519 manifest signatures for production
- HMAC only for dev/mock

## Architecture To Build

Use a modular monorepo with separated runtime processes:

```text
apps/
  control-api/
  device-gateway/
  pop-ingestor/
  orchestrator-worker/
  adapter-workers/
    mock/
    kso/
  admin-web/
  advertiser-web/
  kso-sidecar/
  kso-player/

packages/
  contracts/
  domain/
  authz/
  observability/

infra/
  compose/
  nginx/
  monitoring/
  migrations/
```

Do not start with KSO-specific business tables. Start with:

- channels
- device_types
- physical_devices
- logical_carriers
- display_surfaces
- capability_profiles
- adapter_configs
- manifest_versions
- proof_events
- apply_ack_events
- delivery_events

KSO is implemented as the first adapter and runtime, not as the core model.

## First Implementation Roadmap

### Phase 0 — Architecture Lock

Deliverables:

- ADR-001 deployment and service boundaries
- ADR-002 event bus choice: NATS JetStream baseline
- ADR-003 device identity without required mTLS, mTLS-ready later
- ADR-004 frontend stack: React + TypeScript
- ERD v2.5
- OpenAPI groups
- AsyncAPI/event contracts
- Universal Manifest v1 schema
- Proof Event v1 schema

Acceptance:

- Documents live in `docs/architecture`.
- No code generation yet.
- Hermes can only implement against approved contracts.

### Phase 1 — New Skeleton

Deliverables:

- new repo layout;
- Docker Compose for PostgreSQL, ClickHouse, MinIO, Redis, NATS, services;
- CI commands;
- baseline config/secrets policy;
- health checks;
- logging/correlation ID conventions.

Acceptance:

- `docker compose up` starts infrastructure and empty services;
- migrations apply from zero;
- generated OpenAPI is stable.

### Phase 2 — Enterprise Foundation

Deliverables:

- AD-ready user model and local break-glass admin;
- RBAC/RLS permission catalog;
- organization hierarchy;
- channel/device/surface/capability model;
- audit baseline.

Acceptance:

- one test KSO can be represented as physical device + logical carrier + display surface;
- no KSO-only core business table is required.

### Phase 3 — KSO Pilot Path

Deliverables:

- KSO adapter;
- device onboarding;
- manifest pull with ETag/304;
- Ed25519-signed manifest;
- local sidecar cache;
- PoP batch ingest;
- basic advertiser report snapshot.

Acceptance:

- one test KSO can complete: register -> fetch manifest -> cache media -> play -> send PoP -> show report.

## What To Reuse From Current Repo

Reuse selectively:

- KSO sidecar/player lessons and tests;
- universal manifest validation ideas;
- channel/device/surface terminology;
- RBAC/RLS/audit permission ideas;
- QA documents and acceptance criteria;
- useful test cases that encode real behavior.

Do not reuse as-is:

- current Jinja portal as final frontend;
- one-process backend composition;
- legacy KSO-specific model as core;
- dry-run publication/manifest path;
- docs that claim readiness without production proof.

## Remaining Open Decisions

These are not blocking Phase 0:

1. Exact AD protocol: LDAP bind, SAML, OIDC, Kerberos or corporate proxy.
2. MFA mechanism exposed by AD/IdP.
3. Whether NATS JetStream is acceptable to IT/ops or should be replaced by RabbitMQ.
4. Final retention periods for PoP, audit, logs, creatives and reports.
5. Exact hardware and network details of the first test KSO.
