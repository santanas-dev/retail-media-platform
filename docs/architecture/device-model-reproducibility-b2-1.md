# Device Model Reproducibility — B.2.1

> **Дата:** 2026-06-29 | **Статус:** ✅ COMPLETED

## Problem

B.2 changes (logical_carrier + display_surface for KSO device, placement_target link) were applied via manual SQL. Not reproducible on fresh DB.

## Solution: Idempotent Seed

Added to `backend/app/domains/channels/seed.py`:

### `_seed_kso_device_chain(conn)`
- Finds KSO device by `external_code = 'test-dev-seed'`
- Checks if `kso_player` logical_carrier already exists → skip
- Creates logical_carrier + display_surface with portrait capability profile
- Safe on fresh DB: no-op if KSO device doesn't exist

### `_link_placement_target_to_surface(conn)`
- Finds KSO portrait display_surface
- Updates `placement_targets` with NULL `display_surface_id`
- Idempotent: only affects NULL rows

## Fresh DB Reproducibility

On a fresh DB after migrations + seed:
1. `python -m app.domains.channels.seed` — creates channels, device_types, profiles
2. KSO data migration (A.3) — creates physical_device `test-dev-seed`
3. `python -m app.domains.channels.seed` again — creates LC + DS + links placement_target

## Verification

- Seed runs without errors on existing DB (idempotent)
- B.1+B.2 tests: 34/34
- Backend regression: 882/0
- Portal regression: 842/32sk

## Classification

| Change | Method | Reproducible? |
|---|---|---|
| INSERT logical_carrier | Seed script | ✅ |
| INSERT display_surface | Seed script | ✅ |
| UPDATE placement_target | Seed script | ✅ |
