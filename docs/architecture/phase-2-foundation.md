# Phase 2 — Database Foundation Skeleton

**Date:** 2026-07-02
**Phase:** 2 (Enterprise Foundation — database layer)
**Commit:** (to be committed)
**Previous:** Phase 1.1 (Quality Gates)

## Purpose

Phase 2 adds the PostgreSQL foundation layer: ORM models, Alembic migrations, and a dev seed script for the 11 foundation tables defined in ERD v2.5. No identity, no campaigns, no business logic — just the organizational and channel/device/surface data model.

## What Was Added

### ORM Models (`packages/domain/models.py`)

11 SQLAlchemy tables:

| # | Table | Purpose | Key Columns |
|---|-------|---------|-------------|
| 1 | `branches` | Organization hierarchy | code, name, timezone |
| 2 | `clusters` | Grouping within branches | branch_id FK, code, name |
| 3 | `stores` | Individual retail locations | cluster_id FK, code, name, address |
| 4 | `channels` | Channel catalog | code (KSO/ANDROID_TV/ESL/LED), sort_order |
| 5 | `device_types` | Device type catalog per channel | channel_id FK, code, player_runtime |
| 6 | `capability_profiles` | Display capabilities | device_type_id FK, resolution, formats, pop_mode |
| 7 | `physical_devices` | Physical device registry | store_id FK, device_type_id FK, code, status |
| 8 | `device_certificates` | Device crypto material | physical_device_id FK, cert_type, public_key, fingerprint |
| 9 | `device_status_history` | Authoritative status transitions | physical_device_id FK, old_status, new_status, source |
| 10 | `logical_carriers` | Multi-surface gateways | physical_device_id FK, carrier_type, vendor_config |
| 11 | `display_surfaces` | Individual display surfaces | logical_carrier_id FK, store_id FK, code, resolution |

**Design decisions:**
- All primary keys are UUIDv4 strings (String(36)), not DB-generated — enables offline generation and idempotent seeding.
- `physical_devices.status` is a current-state **cache** — `device_status_history` is the authoritative transition log.
- FKs use RESTRICT by default (SQLAlchemy default) — no accidental cascade deletes.
- No identity tables (users, roles, permissions) yet — Phase 2.x.

### Database Configuration (`packages/domain/database.py`)

- Async SQLAlchemy engine + session factory
- `DATABASE_URL` from environment, dev default to localhost

### Alembic Migration (`apps/control-api/alembic/`)

- `alembic.ini` — points to rewrite schema only
- `alembic/env.py` — imports rewrite models (not old backend models)
- `versions/001_init_channel_model.py` — creates all 11 tables with FKs, unique codes, timestamps

### Dev Seed (`apps/control-api/seed.py`)

Creates one minimal hierarchy:
- 1 branch → 1 cluster → 1 store
- 1 KSO channel → 1 device type → 1 capability profile (1440×1080)
- 1 physical KSO device → 1 logical carrier → 1 display surface

All INSERTs use `ON CONFLICT DO NOTHING` — safe to run repeatedly.

### Tests (`tests/test_phase2_models.py`)

26 tests in 5 test classes:
- `TestPhase2Metadata` — imports, exact 11 tables, all required tables present
- `TestPhase2ModelColumns` — key columns on each model
- `TestPhase2ForeignKeys` — expected FK relationships (10 tests)
- `TestPhase2SeedIdempotency` — ON CONFLICT DO NOTHING on all 9 INSERTs
- `TestPhase2NoOldBackendDependency` — no imports from old backend

### CI Updates

- `.github/workflows/phase1-ci.yml` — added `models.py`, `database.py` to syntax matrix; added `python-tests` job
- `scripts/ci/phase1-checks.sh` — added model test step, added new files to syntax/import list

## How To Verify

### Run model tests (no DB required)

```bash
python -m pytest tests/test_phase2_models.py -v
```

### Run Alembic migration (requires PostgreSQL)

```bash
cd apps/control-api
DATABASE_URL=postgresql://retail_media:retail_media_dev@localhost:5432/retail_media_platform \
  alembic upgrade head
```

### Seed dev data

```bash
DATABASE_URL=postgresql+asyncpg://retail_media:retail_media_dev@localhost:5432/retail_media_platform \
  python apps/control-api/seed.py
```

### Run all Phase 2 checks locally

```bash
bash scripts/ci/phase1-checks.sh
```

## What Was NOT Touched

- `backend/` — old backend code untouched
- `apps/portal-web/` — existing Jinja portal untouched
- `apps/kso_*/` — KSO runtime prototypes untouched
- `.env`, `.gitignore` — untouched
- Docker compose topology — unchanged

## What Is Intentionally NOT Implemented

| Capability | Target Phase |
|-----------|-------------|
| Identity: users, roles, permissions, RBAC/RLS | Phase 2.1 |
| AD/SSO integration | Phase 2.1 |
| Campaigns, placements, inventory | Phase 3 |
| Device onboarding + JWT auth | Phase 3 |
| Manifest generation | Phase 3 |
| PoP pipeline, ClickHouse | Phase 4 |

## Next Steps

1. **Phase 2.1** — Identity foundation: users, roles, permissions, RBAC/RLS, audit
2. **Phase 2.2** — Business core: advertisers, campaigns, placements, inventory rules
