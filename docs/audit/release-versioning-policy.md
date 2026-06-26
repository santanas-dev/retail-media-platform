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

**v0.9.0-product-portal-hardening** (2026-06-25)

Target: `main` branch, commit `0ed9622`.

All Phase 39.2 portal hardening items closed. Ready for 39.3 pre-pilot preparation phase.
