# Backend Regression Baseline Notes

**Task:** 38.12.2 — Backend Regression Stabilization / Pre-Phase-D Gate
**Date:** 2026-06-16
**Commit:** b5e24da (Phase C stabilization)

## Summary

27 pre-existing backend test failures identified. ALL resolved through pytest configuration fix. **Zero code changes to business logic.** Regression returned to clean green baseline.

## Error Catalog

### Category A: PYTHONPATH — 27 failures (2 files)

| Test File | Failures | Root Cause |
|---|---|---|
| `test_z_readiness_gate_383.py` | 14 | `ModuleNotFoundError: No module named 'kso_player'` / `'kso_sidecar_agent'` |
| `test_z_x11_runner_pop_full_e2e_3827.py` | 13 | Same |

**Cause:** These tests import from sibling apps (`apps/kso_player`, `apps/kso_sidecar_agent`) but PYTHONPATH didn't include those directories.

**Fix:** Added `[tool.pytest.ini_options]` with `pythonpath = [".", "../apps/kso_player", "../apps/kso_sidecar_agent"]` to `backend/pyproject.toml`.

**Connection to Phase C:** NONE. These tests predate b5e24da.

### Category B: Script-style integration tests — 8 files (backend-dependent)

| Test File | Error | Type |
|---|---|---|
| `test_step13_1_verify.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step13_pop_ingest.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step14_1_supp.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step14_batch.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step15_operations.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step28_kso_manifest_gateway.py` | `ConnectionRefused` | Needs backend on localhost:8001 |
| `test_step28_kso_media_delivery.py` | `SystemExit: 0` (OK) / `ModuleNotFoundError` (no backend) | Script-style, exits clean when backend available |
| `test_step29_kso_pop_correlation.py` | `ModuleNotFoundError` (no backend) | Script-style |
| `test_step29_kso_pop_ingest_compatibility.py` | `SystemExit: 1` (no backend) | Script-style, needs live credential creation |

**Status:** These are E2E/scenario tests that require a running backend. Not pytest test functions — they execute at module import time and call `sys.exit()`. Excluded via `--ignore=backend/tests/integration` for unit regression.

**Connection to Phase C:** NONE. These files existed before Phase C.

### Category C: Portal-web integration — 9 failures

| Test Class | Failures | Cause |
|---|---|---|
| `TestStoresBackendIntegration` | 4 | Needs live backend |
| `TestDevicesBackendIntegration` | 5 | Needs live backend |

**Status:** Pre-existing. Excluded via `-k "not BackendIntegration"`.

**Connection to Phase C:** NONE. Added in commit 88d2c2c.

## Secret Discrepancy Analysis

- **Phase B secret (32 bytes):** Lost when GatewayDevice was recreated in Phase C. Belonged to a different device registration (legacy `kso_devices` approach).
- **Phase C secret (25 bytes = 24 chars + newline):** Created with new GatewayDevice credential. Stored as bcrypt hash (60 chars, `$2b$` prefix) in `device_credentials` table.
- **Auth consistency:** Verified — manifest sync and media sync both succeeded in Phase C. The sidecar's `device_secret.dev` matches the backend's `device_credentials.secret_hash`.
- **Conclusion:** Different entities, not an error. The current auth chain is consistent.

## Full Regression Results (after fix)

| Suite | Tests | Result |
|---|---|---|
| Backend (unit, excludes integration/) | 292 | ✅ all green |
| Portal-web (excludes BackendIntegration) | 404 | ✅ all green |
| KSO state adapter | 86 | ✅ all green |
| KSO player | 2047 | ✅ + 12 skipped |
| KSO sidecar agent | 1838 | ✅ all green |
| Infra/kso-linux | 227 | ✅ all green |
| **Total** | **4894** | **green baseline** |

## Phase D Gate Assessment

- ✅ All unit tests green (4894 passed)
- ✅ Zero changes to business logic
- ✅ Zero connection to Phase C (b5e24da)
- ✅ Auth chain consistent (secret verified via bcrypt hash + sync success)
- ⚠️ Script-style E2E tests require running backend (not a regression — these are scenario tests)
- ⚠️ Portal-web BackendIntegration tests require running backend (pre-existing)

**Verdict:** Backend regression is at clean green baseline. The pre-existing integration/E2E test gaps are documented and do not block Phase D.
