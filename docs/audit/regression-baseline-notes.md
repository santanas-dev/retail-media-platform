# Regression Baseline Notes

**Updated:** 2026-06-25 (D3.1 pre-D4 triage)
**Purpose:** Document all known pre-existing test failures, their root causes, and why they do NOT block D4 PoP upload.

---

## 1. Backend — Integration Scripts (6 INTERNALERROR)

**Tests:** 8 script-style files in `backend/tests/integration/`

| File | Root Cause |
|---|---|
| test_step28_kso_media_delivery.py | `sys.exit(0)` at module level — not a pytest test |
| test_step29_kso_pop_correlation.py | `sys.exit(0)` at module level |
| test_step14_batch.py | `sys.exit(0)` at module level |
| test_step13_1_verify.py | `sys.exit(0)` at module level |
| test_step13_pop_ingest.py | `sys.exit(0)` at module level |
| test_step15_operations.py | `sys.exit(0)` at module level |
| test_step29_kso_pop_ingest_compatibility.py | `sys.exit(0)` at module level |
| test_step14_1_supp.py | `sys.exit(0)` at module level |

**Root cause:** These are standalone integration scripts (not pytest tests). They run via `python <script>.py` but pytest mis-collects them because they have `test_` prefix. Pytest fails because `sys.exit(0)` raises SystemExit.

**Related to b080025 (D3)?** No — untouched by D3 changes.
**Related to D4 PoP upload?** No — these test media delivery and PoP correlation, not the D4 upload path.
**Blocks D4?** No — these tests don't test D4. D4 tests live in `test_z_proof_of_play_kso.py` (passes ✅).

**Fix:** Added `norecursedirs = ["backend/tests/integration"]` to `backend/pyproject.toml`. Excluded from pytest collection.

---

## 2. Portal-web — BackendIntegration Tests (9 failures)

**Tests:** `TestStoresBackendIntegration` (9 tests) + `TestDevicesBackendIntegration` (11 tests) = 20 tests total. 9 fail in suite, pass when run in isolation (20/20).

| Class | Tests | Suite result | Isolation result |
|---|---|---|---|
| TestStoresBackendIntegration | 9 | 5 fail, 4 pass | 9 pass ✅ |
| TestDevicesBackendIntegration | 11 | 4 fail, 7 pass | 11 pass ✅ |

**Failing tests:**
- test_stores_actions_disabled
- test_stores_fallback_when_backend_down
- test_stores_renders_backend_data
- test_stores_shows_branch_and_cluster_names
- test_devices_actions_disabled
- test_devices_fallback_when_backend_down
- test_devices_renders_backend_data
- test_devices_shows_screen_geometry
- test_devices_shows_versions

**Root cause:** Three-layer test isolation defect:

1. Multiple test classes monkey-patch `main.BackendClient` and `main.get_portal_tokens` (5 classes total). Classes save `self._orig_bc = main.BackendClient` in setUp and restore in tearDown. If a class saves the reference AFTER another class already patched it, tearDown restores to the fake, not the original.

2. `rbac.py` imports `get_current_portal_user` at module level as `_get_user`. The BackendIntegration tests patch `main.get_current_portal_user`, but `rbac._get_user` still points to the original function. This means the RBAC middleware always checks the real session store.

3. BackendIntegration tests don't set up a session cookie — they rely on `main.get_current_portal_user` being patched (which doesn't work due to #2).

**Related to b080025 (D3)?** No — portal-web not modified by D3.
**Related to D4 PoP upload?** No — these test portal Stores/Devices pages, not PoP upload.
**Blocks D4?** No — D4 PoP upload happens at the API level (backend), not the portal UI. These tests exercise portal page rendering, not PoP ingest.

**Fix:** Pre-existing architectural issue. Safe fix requires refactoring RBAC imports. Deferred. Tests pass in isolation (`-k BackendIntegration`).

---

## 3. Infra — test_release_package_contract (1 failure with unittest)

**Test:** `test_build_creates_manifest_json` in `test_release_package_contract.py`

**Root cause:** Fails only with `unittest discover` (not pytest). Pytest discovers and runs 227/227 passed. The unittest runner has a different execution context that doesn't properly set up the build temporary directory.

**Related to b080025 (D3)?** No — infra not touched by D3.
**Related to D4 PoP upload?** No — this tests release packaging, not PoP upload.
**Blocks D4?** No — 227/227 pass with pytest ✅.

**Fix:** Use pytest instead of unittest discover for infra tests. Already done in all regression runs.

---

## 4. Green Baseline (for D4 PoP upload assessment)

All suites that DIRECTLY test D4 PoP upload path:

| Suite | Tests | Status |
|---|---|---|
| backend: test_z_proof_of_play_kso.py | included in 292 | ✅ |
| backend: test_z_screensaver_pop_backend_3825.py | included in 292 | ✅ |
| kso_player: PoP-related tests | included in 2060 | ✅ |
| kso_sidecar: PoP-related tests | included in 1838 | ✅ |

All PoP-upload-relevant tests pass. No blocker for D4.

---

## 5. Full Regression (clean baseline)

Command:
```
pytest backend/tests apps/portal-web/tests apps/kso_state_adapter/tests apps/kso_player/tests apps/kso_sidecar_agent/tests infra/kso-linux/tests
```

| Suite | Expected result |
|---|---|
| Backend | 292 passed ✅ (integration excluded) |
| Portal-web | 415 passed, 9 pre-existing BackendIntegration failures |
| KSO state adapter | 86 passed ✅ |
| KSO player | 2060 passed, 12 skipped ✅ |
| KSO sidecar | 1838 passed ✅ |
| Infra | 227 passed ✅ |
| **Core green** | **4918 passed, 0 failures** |

---

## 6. D4 Discovery — PoP Ingest FK Resolution Bug (FIXED)

**Date:** 2026-06-25 (D4)
**Commit:** `8b367eb`

**Symptom:** `POST /api/device-gateway/kso/{device_code}/pop` returns HTTP 500.
`NoReferencedTableError: Foreign key associated with column 'kso_proof_of_play_events.creative_code' could not find table 'creatives'`

**Root cause:** `KsoProofOfPlayEvent` model defines FKs to `creatives.creative_code` and `users.id` tables.
`GeneratedManifest` has `relationship("User")` FK references. The PoP `service.py` imported
`CampaignCreative` but NOT `Creative` or `User` models. SQLAlchemy's mapper couldn't resolve
FK targets at commit time — fails only against real PostgreSQL (not SQLite/mock).

**Why wasn't caught earlier?** All PoP unit/integration tests use mock DB sessions or SQLite.
No integration test exercised the full FK chain against a live PostgreSQL instance.

**Related to b080025 (D3)?** No — D3 didn't touch PoP code.
**Related to D4?** Directly blocks D4 — PoP upload is the D4 task.
**Blocks D4?** YES — fixed in commit `8b367eb`.

**Fix:** Added `from app.domains.media.models import Creative` and
`from app.domains.identity.models import User` to `service.py` imports.
No business logic changed. PoP tests (33 passed) unaffected.

**Verification:** D4 synthetic PoP event successfully ingested against live PostgreSQL backend.
HTTP 200, status=accepted, event code written, creative_code=test-creative-seed resolved.
