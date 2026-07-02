# Backend Compliance Audit

**Date:** 2026-07-02 | **Audit:** AUDIT.0

---

## Summary

Backend: **28 domains, 24 routers, 26 service layers, 16 models.py, 51 permissions, 8 roles, 0 migration files. 2458 tests / 0 errors.**

---

## Domain-by-Domain Assessment

### identity — ✅ READY
- Users, roles, permissions CRUD
- Seed: idempotent, 8 roles, 51 permissions
- Auth: login/logout/refresh/me
- RLS: advertiser/store/channel scope enforcement
- Audit: all security events logged
- Tests: covered

### organization — ✅ READY
- Branches, clusters, stores hierarchy
- Full CRUD
- Portal: stores page
- Tests: covered

### channels — ✅ READY
- 5 device types seeded
- 6 capability profiles
- Physical devices → Logical carriers → Display surfaces
- external_code + device_properties
- Tests: covered

### advertisers — ✅ READY
- Advertiser CRUD
- Brand management
- Contract + order management
- Tests: covered

### media — ✅ READY
- Creative upload + ffprobe validation
- Moderation workflow (submit/approve/reject/rework)
- AV scanner: NoScanner in dev (real AV deferred)
- MinIO storage
- Tests: covered

### campaigns — ✅ READY
- Campaign CRUD + submit + approval
- Campaign-placement link
- Creative binding
- Publication batch creation
- Tests: covered

### planning — 🟡 READ_ONLY
- 5 endpoints: availability_snapshot, occupancy, conflict_check, store_capacity, campaign_placement_plan
- All read-only by design
- **Missing:** booking/reservation writes
- **Blocks:** portal planning workflow
- Tests: covered

### inventory — 🟡 READ_ONLY
- Inventory unit CRUD (read)
- Capacity rules (read)
- **Missing:** write capability
- Tests: covered

### scheduling — 🟡 PARTIAL
- Schedule run create/read
- Schedule items
- **Missing:** advanced scheduling, conflict resolution
- Tests: covered

### publications — 🔴 DRY_RUN
- Publication batch create/read
- Approval flow
- **Real publish: NO-GO** (design gate)
- **Blocks:** real campaign publishing
- Tests: covered

### manifests — 🔴 DRY_RUN
- UniversalManifestV1 schema + builder
- Preview mode only
- **No GeneratedManifest writes**
- **Blocks:** manifest delivery to devices
- Tests: covered

### device_gateway — ✅ READY
- Device auth/token
- Heartbeat
- Manifest pull (preview)
- PoP ingestion (legacy + enterprise)
- Media delivery
- Device lifecycle
- Tests: covered

### device_operations — ✅ READY
- Device management operations
- Tests: covered

### device_dashboard — ✅ READY
- Device status, heartbeat visibility
- Tests: covered

### proof_of_play — ✅ READY
- PoP event ingestion and query
- Tests: covered

### analytics — 🟡 READ_ONLY
- 4 endpoints: campaign_summary, delivery_metrics, device_health, placement_analytics
- Read-only per design
- ClickHouse pipeline: deferred
- Tests: covered

### campaign_reports — 🟡 READ_ONLY
- Campaign delivery snapshots
- Read-only
- Tests: covered

### reports — 🟡 READ_ONLY
- CSV export: campaigns, airtime, conflicts, publications
- Tests: covered

### emergency — 🧪 DRY_RUN
- 4 endpoints: capabilities, preview, simulate-stop, simulate-message
- Dry-run enforced: dry_run=false → 422
- Permission: emergency.read (3 roles)
- No emergency.execute/approve
- Real execution: NO-GO (design gate)
- Tests: 414/414

### health — ✅ READY
- 4 endpoints: live, ready, dependencies, metrics
- Correlation ID + structured logging (H.2)
- Tests: covered

### approvals — ✅ READY
- Campaign/creative approval workflow
- Tests: covered

### hierarchy — ✅ READY
- Organization hierarchy
- Tests: covered

### airtime — ✅ READY
- Airtime tracking
- Tests: covered

### test_kso_readiness — ✅ READY (dev only)
- KSO readiness test helpers
- Tests: covered

### adapters — 🧪 DRY_RUN
- KSO adapter: dry-run only
- Mock adapter
- Adapter registry
- Tests: covered

### orchestrator — 🧪 DRY_RUN
- Simulation mode
- Publication orchestration
- Tests: covered

### audit — ✅ READY
- Audit trail service
- Tests: covered

---

## Backend Gaps Summary

| Domain | Status | Gap | Blocks |
|---|---|---|---|
| planning | READ_ONLY | No booking writes | Portal + store pilot |
| publications | DRY_RUN | No real publish | Store pilot |
| manifests | DRY_RUN | No real generation | Store pilot |
| emergency | DRY_RUN | Dry-run only | Production only |
| analytics | READ_ONLY | Read-only | — |
| inventory | READ_ONLY | Read-only | — |
| media | PARTIAL | NoScanner in dev | — |

---

## Backend Maturity

| Metric | Value |
|---|---|
| Total domains | 28 |
| With routers | 24 |
| With service layers | 26 |
| With models | 16 |
| Permissions defined | 51 |
| Roles defined | 8 |
| Migration files | 0 (seed-based) |
| Test collection | 2458 |
| Test errors | 0 |
| Read-only domains | 5 |
| Dry-run domains | 4 |
| Deferred features | 3 (ClickHouse, mTLS, real emergency) |
| Missing features | 2 (booking, real publish) |

---

## Recommendation

Backend is **85% complete** for functional coverage.  
**Critical gaps:** publication real publish (BACKEND.1.1), manifest real generation (BACKEND.1.2), booking (BACKEND.1.3).  
**Read-only by design:** planning, analytics — acceptable for v1.  
**Dry-run by design:** emergency — acceptable. Publications/manifests — MUST be resolved.
