# Retail Media Platform: Enterprise Architecture Review

## Executive Verdict

ТЗ v2.5 описывает не MVP и не "портал для КСО", а enterprise retail media platform:
channel-agnostic core, Channel Orchestrator, Channel Adapter Layer, подписанный
manifest, нормализованный Proof, SLA, компенсации, staged rollout, audit,
observability и отдельные контуры для пользовательского API и устройств.

Starting decisions for the rewrite are fixed in
`analysis/rmp_rewrite_starting_decisions.md`: Docker-first deployment, React +
TypeScript frontend, AD identity, one-test-KSO pilot, NATS JetStream as the
recommended event-bus baseline, and non-legal advertiser PDF reports.

Текущий репозиторий ценен как прототип и база знаний: в нем уже есть домены,
контракты, KSO sidecar/player, universal manifest draft, channel/device model,
tests и много QA-документов. Но как enterprise foundation его лучше переписать:
оставить идеи, тесты и отдельные реализации, но пересобрать архитектуру вокруг
четких сервисных границ, контрактов и событийной модели.

## What The TZ Actually Requires

Core scale and constraints:

- до 10 000 магазинов;
- 40 000+ КСО плюс Android/TV, price checker, ESL, LED и будущие носители;
- polling manifest каждые 30 секунд с jitter и HTTP 304/ETag;
- PoP десятки/сотни миллионов событий в год;
- PoP хранится минимум 3 года, точный срок утверждают бизнес и юристы;
- Control Plane доступность 99.5%, Device Gateway 99.9%;
- emergency delivery до 60 секунд на 95% online devices;
- автономная работа устройств минимум 7 дней по последнему валидному manifest;
- административный доступ только из корпоративной сети/VPN через AD/SSO/MFA;
- устройства инициируют исходящие соединения к Device Gateway, входящие из ЦОД
  к магазинам не являются базовой моделью.

The critical architectural decision is:

```text
channel-agnostic core + channel-specific adapters
```

KSO is only the first production channel. It must not become the architecture.

## Current Repository Assessment

Observed current shape:

- `backend/app`: 304 files, 152 Python files.
- `backend/app/domains`: 28 domain folders.
- `backend/tests`: 89 test files.
- `backend/alembic/versions`: 34 migration files.
- `apps`: 563 files, 259 Python files.
- `apps/portal-web`: FastAPI + Jinja2 server-rendered portal, not React/TypeScript.
- `apps/kso_player`, `apps/kso_sidecar_agent`, `apps/kso_state_adapter`: useful KSO
  runtime prototypes.
- `docs`: 346 markdown files, many phase reports and design gates.

Strong parts worth preserving:

- channel/device model draft: `channels`, `device_types`, `physical_devices`,
  `logical_carriers`, `display_surfaces`, `capability_profiles`;
- `orchestrator` and adapter contract sketches;
- universal manifest schema validation ideas;
- device gateway auth/session/heartbeat/PoP draft;
- KSO player/sidecar/state-adapter safety lessons;
- RBAC/RLS/audit concepts;
- test and QA mindset.

Main architectural problems:

- One FastAPI app currently owns too much: user API, device gateway, planning,
  publications, PoP, analytics, emergency, health and admin concerns.
- Portal is Jinja/server-rendered, while TZ recommends React + TypeScript for
  enterprise admin workflows.
- Several areas are dry-run/read-only/deferred: real publication, real manifest
  generation, ClickHouse pipeline, mTLS, real emergency, production rollout.
- Legacy KSO-specific entities still coexist with universal channel model.
- Some docs claim readiness that code/design later contradicts.
- Operational production platform is incomplete: HA, CI/CD, secrets, monitoring
  deployment, backup drills, load tests and physical KSO tests are not yet real.

## Recommended Target Architecture

Use a modular monorepo, but split runtime processes by load and blast radius.
Avoid a distributed microservice maze on day one; do not keep everything in one
process either.

```text
apps/
  control-api/          FastAPI user/admin API, business control plane
  device-gateway/       FastAPI/async service for devices and adapters
  pop-ingestor/         high-throughput validation and event intake
  orchestrator-worker/  manifest generation, simulation, rollout tasks
  adapter-workers/      kso, android-tv, price-checker, esl, led, mock
  admin-web/            React + TypeScript internal portal
  advertiser-web/       React + TypeScript advertiser portal
  kso-sidecar/          local device agent
  kso-player/           Chromium/runtime player

packages/
  contracts/            OpenAPI, AsyncAPI, manifest schema, event schema
  domain/               shared domain primitives, enums, IDs, errors
  authz/                RBAC/RLS helpers and permission catalog
  observability/        logging, tracing, metrics conventions

infra/
  compose/              local development
  k8s-or-vm/            production deployment manifests/runbooks
  migrations/           DB migrations and schema checks
```

Recommended runtime boundaries:

- Control Plane: users, roles, advertisers, contracts/orders, campaigns,
  approvals, inventory, content metadata, publications, reporting queries.
- Device Gateway: registration, short-lived device sessions, manifest pull,
  heartbeat, media access authorization, apply-ack, command polling.
- PoP/Event Ingestion: batch validation, signature/HMAC/mTLS verification,
  idempotency, enqueue, ClickHouse write, dead-letter handling.
- Channel Orchestrator: target surface resolution, simulation, conflict
  detection, manifest generation, signing, rollout/rollback, adapter task
  creation.
- Adapter Layer: isolated workers for KSO, Android/TV, price checker, ESL,
  LED and mock adapters. No direct PostgreSQL/ClickHouse/MinIO access except
  through approved APIs/events.
- Analytics/Reporting: ClickHouse aggregates, advertiser reports, SLA reports,
  immutable report snapshots and exports.

## Technology Choices

Keep the TZ stack, but harden the interpretation:

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic.
- Frontend: React + TypeScript, preferably Vite or Next only if SSR is required.
- PostgreSQL: transactional source of truth with strict migrations.
- ClickHouse: PoP, heartbeat, proof, telemetry, audit analytics and aggregates.
- Redis: cache, rate limits, sessions, short-lived locks.
- Event bus: NATS JetStream as first production choice for simpler operations;
  keep an abstraction so Redpanda/Kafka can replace it if corporate standards
  or throughput demand it.
- MinIO: versioned media, generated manifest packages, report artifacts.
- Observability: OpenTelemetry, Prometheus, Grafana, Loki/ELK, alert rules.
- Secrets: Vault, corporate secret storage, or at minimum environment-based
  secrets with rotation and no secrets in repo/logs.
- Manifest signing: Ed25519 for production; HMAC only for dev/mock.
- Device auth: mTLS if corporate PKI allows it; otherwise device certificate
  or long-lived credential exchange for short-lived JWT, never token in URL.

## Domain Model To Build First

Foundation:

- Organization: network, branch, cluster, store, store zones, calendars/timezones.
- Identity: users, roles, permissions, groups, RLS scopes, MFA policy, audit.
- Advertisers: advertiser, brand, contract, order, contacts.
- Channels: channel, device type, physical device, logical carrier,
  display surface, capability profile, adapter config, runtime version.
- Content: media asset, creative, creative version, rendition, QA result,
  moderation task, preview.
- Campaign: campaign, placement, target, workflow status, status history,
  approval route.
- Inventory: inventory unit, capacity rule, reservation, booking, forecast,
  conflict, sold-out reason.
- Manifest: manifest version, manifest target, manifest item, adapter payload,
  signature, compatibility metadata.
- Events: proof event, delivery ack, apply ack, heartbeat, error, command event.
- Operations: rollout plan, rollout step, feature flag, emergency event,
  incident, backup/restore evidence.
- Reporting: report snapshot, export job, advertiser report, SLA report,
  compensation proposal.

## Functional Gaps Beyond The TZ

The TZ is strong, but enterprise delivery also needs these explicit additions:

- Notification center: approvals, moderation comments, failed rollout, SLA breach,
  emergency, export ready, device incident.
- Workflow engine or state-machine library for approvals, publication, rollout,
  report generation and emergency. Start with explicit DB state machines; consider
  Temporal only if the team can operate it.
- Commercial package model: bundles, sponsorship packages, category exclusivity,
  share-of-voice guarantees, bonus/compensation rules.
- Forecasting quality loop: compare forecast vs actual PoP and adjust inventory
  predictions.
- Data quality and reconciliation: device counts, store closures, duplicate
  surfaces, stale capability profiles, mismatched SKU/category mappings.
- Master data integrations: store master, product/category/SKU master, price
  master, check/traffic aggregates, AD/SSO, BI/DWH.
- Support workflows: device incident assignment, comments, SLA owner, maintenance
  windows, escalation.
- Report immutability: signed report snapshots, report versioning, regeneration
  policy, legal wording approval.
- Audit tamper resistance: append-only audit, SIEM export, admin review workflow.
- Release governance: CI/CD gates, DB migration checks, contract compatibility
  tests, seed-data performance tests, rollback drills.
- Accessibility and UX governance: design system, role-based navigation, saved
  filters, bulk operations, keyboard support.

## Rewrite Strategy

Do not rewrite blindly. Treat the current repo as a prototype library.

Phase 0: Decisions and contracts

- Freeze old repo for reference.
- Write ADRs: modular runtime boundaries, event bus, signing, device auth, frontend
  stack, deployment target, retention, report legal status.
- Produce ERD v2.5, OpenAPI groups, AsyncAPI/event contracts, manifest schema,
  proof schema.

Phase 1: Enterprise foundation

- New monorepo layout.
- CI, lint, tests, migration check, OpenAPI generation, contract tests.
- PostgreSQL baseline migrations.
- Identity/RBAC/RLS/audit and organization hierarchy.
- Channel/device/surface/capability model.

Phase 2: Business core

- Advertisers/contracts/orders.
- Campaigns/placements/workflow.
- Content/renditions/Creative QA.
- Inventory rules, forecast, reservations, conflict simulation.

Phase 3: Orchestration and delivery

- Channel Orchestrator worker.
- Universal manifest v1 with Ed25519 signing.
- Mock adapter first, KSO adapter second.
- Device Gateway with registration, heartbeat, manifest ETag/304, media auth.

Phase 4: Proof and analytics

- PoP batch ingest, idempotency, signature verification.
- Event bus and ClickHouse pipeline.
- SLA, underdelivery reasons, report snapshots, exports.

Phase 5: Production readiness

- React admin portal and advertiser portal.
- Feature flags, staged rollout, rollback.
- Emergency execution path.
- Observability, backup drills, load tests, 1-KSO physical pilot.

## Keep / Rewrite Decision

Keep as reference or port selectively:

- channel model names and seed ideas;
- universal manifest schema tests;
- KSO sidecar/player local safety logic;
- RBAC/RLS permission catalog;
- QA documents and acceptance criteria;
- tests that encode real business behavior.

Rewrite:

- app packaging and service boundaries;
- portal frontend;
- migrations and schema baseline;
- publication/manifest/orchestration as event-driven workflows;
- PoP pipeline into ClickHouse;
- device auth and manifest signing;
- deployment/operations layer.

## Questions To Resolve Before Coding

1. Production deployment target: bare VMs, Docker Compose, Kubernetes/OpenShift,
   or corporate PaaS?
2. Corporate standard for event bus: NATS, RabbitMQ, Kafka/Redpanda, or something
   already approved?
3. Is corporate PKI/mTLS available for device certificates?
4. Which AD/SSO provider and MFA method must be used?
5. What is the first real pilot scope: 1 KSO, 10 stores, or immediate multi-store?
6. Are Android/TV, price checker, ESL and LED in scope for v1 contracts only or
   for actual pilot delivery?
7. Which system is master for prices/SKU/category/store hierarchy/check data?
8. What legal status should advertiser PDF reports have?
9. Approved retention periods for PoP, audit, technical logs, creatives and reports?
10. Is React + TypeScript approved, and do we need a separate advertiser portal
    in the first release?
