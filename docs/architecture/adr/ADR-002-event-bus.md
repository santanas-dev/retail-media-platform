# ADR-002: Event Bus — NATS JetStream Baseline

**Status:** Accepted
**Date:** 2026-07-02
**Phase:** 0 (Architecture Lock)
**Deciders:** Sergey Paschenko (project owner), Hermes Agent

## Context

ТЗ v2.5 §24.9 requires an event-driven architecture for multi-channel delivery. Direct synchronous calls from portal to device/vendor are NOT the primary mechanism for mass publication. An event bus is needed for:

- PoP batch ingestion (40 000 devices × PoP every 60s → millions/day)
- Manifest generation tasks dispatched to adapters
- Device events (heartbeat, errors, apply-ack)
- Emergency command distribution
- Inter-service communication (Orchestrator → Adapters → Device Gateway)

The `rmp_rewrite_starting_decisions.md` states: no corporate broker is currently approved. Baseline recommendation: NATS JetStream.

## Decision

**NATS JetStream as the first production event bus, behind an internal event-bus abstraction.**

### Why NATS JetStream

| Criterion | NATS JetStream | RabbitMQ | Kafka/Redpanda |
|-----------|---------------|----------|----------------|
| Operations complexity | Low (single binary, embedded) | Medium | High (ZooKeeper/KRaft) |
| Throughput | Very high (millions msg/s) | Medium-high | Very high |
| Persistence | JetStream streams | Queues with persistence | Log-based, infinite retention |
| Docker-fit | Excellent | Good | Heavy |
| Enterprise approval risk | Unknown | Commonly approved | Commonly approved |
| Migration path | Replaceable via abstraction | Replaceable | Replaceable |

### Abstraction Layer

All services publish/consume through `packages/events/` — a thin abstraction that:

- Exposes `publish(subject, payload)`, `subscribe(subject, handler)`, `request(subject, payload, timeout)`
- Encapsulates NATS-specific connection, reconnection, authentication
- Allows replacing NATS with RabbitMQ/Kafka/Redpanda without touching business logic
- Supports mock implementation for local development and testing

### Core Subjects

| Subject Pattern | Publisher | Consumer(s) | JetStream |
|----------------|-----------|-------------|-----------|
| `pop.ingest.batch` | Device Gateway | PoP Ingestor | Yes (persisted, idempotent) |
| `device.heartbeat` | Device Gateway | Analytics, Monitoring | No (ephemeral, fire-and-forget) |
| `device.apply.ack` | Device Gateway | Orchestrator Worker | Yes (persisted) |
| `device.error` | Device Gateway | Monitoring | No |
| `manifest.generate.request` | Control API | Orchestrator Worker | Yes (persisted, exactly-once) |
| `manifest.generated` | Orchestrator Worker | Device Gateway | Yes (persisted) |
| `adapter.*.task` | Orchestrator Worker | Adapter Workers | Yes (persisted, queue group) |
| `adapter.*.result` | Adapter Workers | Orchestrator Worker | Yes (persisted) |
| `emergency.execute` | Control API | Orchestrator Worker | Yes (high priority, persisted) |
| `audit.event` | All services | Audit Logger → PostgreSQL | Yes (persisted) |

### Non-Goals / Deferred

- Exactly-once semantics initially: at-least-once with idempotency keys is sufficient for Phase 1–3.
- Advanced stream configurations (mirroring, sourcing) deferred to production hardening.
- NATS Operator/K8s operator deferred until deployment platform is confirmed.

## Consequences

- **Positive:** Lightweight, single-binary, Docker-native; excellent throughput; simple operations.
- **Negative:** Less enterprise recognition than Kafka; IT/ops approval not yet obtained.
- **Risk:** If IT mandates RabbitMQ or Kafka, the abstraction layer and subject topology remain valid; only the transport implementation changes.
- **Mitigation:** Abstraction from Day 1. All services use `packages/events/`, never import NATS client directly.

## References

- TZ v2.5 §24.9 (Event-driven architecture)
- `rmp_rewrite_starting_decisions.md` — Confirmed event broker baseline
- `rmp_enterprise_architecture_review.md` — Technology choices
