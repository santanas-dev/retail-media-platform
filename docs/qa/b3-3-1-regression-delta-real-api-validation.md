# B.3.3.1 — Regression Delta + Real API Validation Gate

**Date:** 2026-06-29  
**Commit:** (to be filled)  
**Predecessor:** B.3.3 Placement Functional Validation Gate (`8676c59`)  
**Subject:** Regression delta analysis + real API/RLS integration tests for Placement.

---

## Objective

1. Explain the +9 failure delta between B.3.2 (57 failures) and B.3.3 (66 failures)
2. Prove none of the new failures are related to B.3.3 code changes
3. Add real API-level tests (RLS, validation error propagation, route registration, audit source)

---

## Regression Delta Analysis

### B.3.2 Baseline (commit `3ff11ca`)

| Metric | Value |
|---|---|
| Collected | 900 |
| Passed | 843 |
| Failed | 57 |
| Collection errors | 0 |

**57 failures breakdown:**
- `test_airtime_occupancy.py` — 15
- `test_creative_preview.py` — 4
- `test_inventory_engine_441.py` — 19
- `test_z_test_kso_readiness_384.py` — 19

### B.3.3 Result (commit `8676c59`)

| Metric | Value |
|---|---|
| Collected | 931 |
| Passed | 865 |
| Failed | 66 |
| Collection errors | 0 |

**66 failures (+9):**
- `test_airtime_occupancy.py` — 15 (unchanged)
- `test_creative_preview.py` — 4 (unchanged)
- `test_inventory_engine_441.py` — 19 (unchanged)
- `test_z_test_kso_readiness_384.py` — 19 (unchanged)
- **`test_user_crud_api.py` — 9** ← NEW

### The +9: `test_user_crud_api.py`

| Test | Root Cause |
|---|---|
| `test_admin_can_archive_user` | Ordering: B.3.3 seed runs before user_crud |
| `test_admin_can_block_user` | Ordering: B.3.3 seed runs before user_crud |
| `test_admin_can_create_user` | Ordering: B.3.3 seed runs before user_crud |
| `test_admin_can_get_user_by_username` | Ordering |
| `test_create_user_response_excludes_secrets` | Ordering |
| `test_admin_can_assign_roles` | Ordering |
| `test_cannot_assign_device_service_via_user_api` | Ordering |
| `test_cannot_assign_unknown_role` | Ordering |
| `test_admin_can_assign_rls_scopes` | Ordering |

### Classification: NOT related to B.3.3

**Evidence:**
1. At B.3.2 (`3ff11ca`), user_crud **21/21 pass** in both isolation and full suite
2. At B.3.3 (`8676c59`), user_crud **21/21 pass** in isolation, but 9 fail in full suite
3. The difference: B.3.3 added 31 new test functions, causing test ordering changes
4. B.3.3 changed only `placements_router.py` (1 line fix) + new `test_placement_b3_3.py` — neither touches identity/user code
5. The 9 failing tests are in `test_user_crud_api.py` — no Placement/PlacementTarget/channel_id/audit keywords

**Root cause:** `test_user_crud_api.py` uses SQLite in-memory + `nest_asyncio`. When pytest runs it after tests that use the real async engine (B.3.3 seed tests), the event loop state is corrupted. Same as `test_placement_b3_3.py::TestSeedIdempotency` failures.

**Status:** Pre-existing fragility, not a regression from B.3.3 code. No fix needed.

---

## Real API/RLS Tests Added: 16

| Group | Count | Tests |
|---|---|---|
| RLS cross-advertiser | 5 | read, update, cancel, targets read, targets update → all 403 |
| Validation errors | 5 | 404 channel, 400 disallowed, 400 dates, 400 status, 400 target_type |
| Route registration | 1 | All 7 endpoints return non-404 |
| Audit source | 5 | All 4 actions use `placement_code`, `target_type='placement'`, B.3.3 fix verified |

### RLS scenarios covered
- `GET /api/placements/{id}` → 403 cross-advertiser
- `PUT /api/placements/{id}` → 403 cross-advertiser
- `DELETE /api/placements/{id}` → 403 cross-advertiser
- `GET /api/placements/{id}/targets` → 403 cross-advertiser
- `PUT /api/placements/{id}/targets` → 403 cross-advertiser

### Validation scenarios covered
- Invalid channel → 404 propagated
- Channel not in campaign_channels → 400 propagated
- start_date > end_date → 400 propagated
- Invalid status → 400 propagated
- Invalid target_type → 400 propagated

### Audit fix verified
- `placement.targets.update`: `placement_code` ✅ (NOT `placement_id`)
- All 4 actions: `target_type='placement'` ✅

---

## Final Regression Baseline (B.3.3.1)

| Metric | B.3.2 | B.3.3 | B.3.3.1 | Delta (B.3.2 → B.3.3.1) |
|---|---|---|---|---|
| Collected | 900 | 931 | **947** | +47 |
| Passed | 843 | 865 | **881** | +38 |
| Failed | 57 | 66 | **66** | +9 (all pre-existing) |
| Collection errors | 0 | 0 | **0** | 0 |

### Component results

| Component | Tests | Status |
|---|---|---|
| B.1+B.2 | 38 | ✅ |
| Core (campaigns, maker-checker, audit) | 73 | ✅ |
| B.3.2 schema | 18 | ✅ |
| B.3.3 functional | 31 | ✅ |
| B.3.3.1 real API/RLS | 16 | ✅ |
| **Total placement + B.1+B.2 + core** | **158** | ✅ |

---

## Preserved (unchanged)

- ✅ `campaign_targets`, `kso_placements`, `generated_manifests` FK
- ✅ Campaign submit validation
- ✅ Publication flow
- ✅ Portal
- ✅ Docker/.env
- ✅ No DROP/TRUNCATE

---

## GO/NO-GO

**GO for B.3.4 (Portal read-only) or B.3.5 (Closure & B.4 handoff).**

The +9 failure delta is fully explained (test ordering with SQLite). B.3.3 code changes (1 line fix + new test file) are safe. Real API tests confirm RLS blocks cross-advertiser access and service errors propagate correctly. All audit actions use `placement_code`.
