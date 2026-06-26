# Release Versioning Policy

> **Status:** POLICY
>
> Date: 2026-06-25
> Scope: Retail Media Platform — all components (backend, portal, KSO player/sidecar/adapter, infra)

---

## SemVer

`MAJOR.MINOR.PATCH` — [Semantic Versioning 2.0.0](https://semver.org/).

| Component | Meaning |
|---|---|
| **MAJOR** | Breaking changes: API incompatibility, data model migration, protocol change, auth model change. Any change that breaks existing contracts or requires coordinated fleet update. |
| **MINOR** | Backward-compatible new functionality: new domain, new endpoint, new page, new feature. Regression must remain green. |
| **PATCH** | Backward-compatible fixes: bugfix, regression fix, doc update, test addition without new feature, security hardening without API change. |

---

## v0.x — Pre-Pilot Development

Все версии до **v1.0.0** — pre-pilot development. API, протоколы и контракты могут меняться между минорами. Стабильность гарантируется regression baseline, но не backward compatibility.

### v0.5.0 — Test KSO Phase A Readiness

- Test KSO virtual device + seed data
- Backend API foundation (campaigns, creatives, devices, etc.)
- Portal framework (FastAPI + Jinja2 server-side rendering)
- RBAC permissions foundation
- Regression baseline: ~3000 tests

### v0.6.0 — Sidecar Config Readiness

- KSO sidecar agent config + health checks
- Sidecar ↔ player communication contract
- Initial PoP ingest (test-kso only)
- First physical KSO smoke test framework
- Regression baseline: ~3500 tests

### v0.7.0 — One-KSO E2E Dry Run

- Phase D: D0–D6 completed on physical KSO (192.168.110.223)
- X11 screensaver runner (768×1024 portrait)
- Click-through proof, guarded runner, kill-switch
- PoP E2E: player → JSONL → sidecar → backend ingest → portal report
- Physical KSO visual confirmation
- Regression baseline: ~4900 tests
- **NOT pilot-ready**: HW scanner validation postponed, controlled long-run required

### v0.8.0 — Device Gateway / Backend API Hardening

- Device auth foundation (JWT, bcrypt, constant-time comparison)
- Campaign/placement production APIs (code-based endpoints)
- Schedule backend API (Schedule + ScheduleSlot models)
- Manifest production list endpoint
- Device gateway PoP ingest + manifest endpoints secured
- Regression baseline: ~4900 tests

### v0.9.0 — Product Portal Hardening

- Portal Schedule UI → backend-driven (remove demo)
- Portal Campaign UI → production API (create/edit/archive/creative binding)
- Portal Dashboard → real KPI from backend list endpoints (remove demo)
- Portal Reports → production PoP backend + active server-side filters
- RBAC: schedule/campaign/reports permissions aligned with backend
- All demo_data references removed from Schedule, Campaign, Dashboard, Reports
- Regression baseline: 4976 tests
- **NOT pilot-ready**: HW scanner, controlled long-run, charts/Excel/drill-down, mTLS/rotation deferred

### v0.10.0 — Approval / Publication Workflow Hardening

- Production approval endpoints: GET/POST /api/approvals, approve/reject per-code
- Approval guardrails: maker-checker, state validation, duplicate prevention
- Publication batch state machine: draft → pending_approval → approved → manifest_generated → published
- Batch approval request: POST /api/publication-batches/{id}/request-approval creates ApprovalRequest
- Approved ApprovalRequest required for batch approve/generate/publish
- Unified manifest generation: build_manifest_from_placement() — single builder for production + legacy
- Production manifest endpoints: POST /api/manifests, GET /api/manifests/{code}, POST /api/manifests/{code}/publish
- Portal approvals page: production backend-driven, publication_batch support, no test-kso wording
- Portal publications page: production endpoints, backend-status-only labels, no demo placeholders
- All responses safe projection (no raw UUID/secrets/tokens/backend_url)
- Regression baseline: 5042 tests (backend 379, portal 440, state 86, player 2072, sidecar 1838, infra 227)
- Commits: 3fc003c → fe03de4 → 58735d9 → d16a14e → 30ac341
- **Deferred**: physical manifest delivery to KSO, sidecar sync, scanner validation, controlled long-run, pilot runbook, mTLS/nonce/rate-limit, charts/Excel/drill-down, full RLS enforcement

### v1.0.0 — First Pilot Release (future)

Gate conditions:

- HW scanner E2E validation completed
- Controlled long-run (≥48 hours, multi-day campaign)
- Fleet runbook documented
- BackendIntegration failures resolved
- mTLS/nonce/rate-limit on device gateway
- RLS full enforcement
- No test-kso endpoints used as production path
- Regression baseline stable

---

## Patch Versions

Patch versions (MAJOR.MINOR.**PATCH**) are released for:

- Bugfix (без API изменения)
- Regression fix
- Documentation update
- Test addition (без нового функционала)
- Security hardening without contract change

Patch release process:

1. Regression must remain green
2. `git tag -a vX.Y.Z -m "Patch: <description>"`
3. CHANGELOG updated

---

## Current Release

**v0.10.0-approval-publication-hardening** (2026-06-26)

Target: `main` branch, commit `30ac341`.

All Phase 39.3 approval/publication hardening items closed. Backend workflow complete — physical KSO delivery is the next gate.

### Post-v0.10.0 Hardening (on main, not yet tagged)

| Step | What | Commit | Regression |
|---|---|---|---|
| 39.4 | Device/Sidecar Dashboard (7 GAPs) | `5557563` | 5103 green |
| 40.0 | TZ Alignment / Security & RLS Audit | `3628c3f` | 5079 green |
| 40.1 | RLS Hardening P0 | `d00858d` | 5096 green |
| 40.1.2 | RLS Gate Closure | `fabf13d` | 5116 green |
| 40.1.3 | Regression Baseline Cleanup | `1b51894` | 5106 green |
| 40.2 | Admin Audit Hardening | `8ff648a` | 5124 green |
| 40.3 | Pilot Readiness Gates Plan | TBD | 5124 green |

### v0.11.0 — Pilot Readiness Gates (next)

Gate conditions:

- HW scanner E2E validation completed
- Controlled long-run (≥1h) completed
- Full regression green (all suites)
- RLS gate closed (confirmed)
- Audit trail active (all domains)
- Device dashboard healthy
- Pilot runbook finalized
- All approval tokens issued and consumed cleanly

Target tag: `v0.11.0-pilot-readiness-gates`
