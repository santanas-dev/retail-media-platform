# Regression Classification — 45.6.1

## Portal: 3 Pre-Existing Failures (RESOLVED)

All 3 were live-integration tests that failed due to stale server process:

| # | Test | File | Error | Resolution |
|---|------|------|-------|------------|
| 1 | `test_admin_accesses_campaigns` | `test_portal_backend_live_integration.py:219` | `None != 200` | Portal server restart |
| 2 | `test_admin_accesses_schedule` | `test_portal_backend_live_integration.py:231` | `None != 200` | Portal server restart |
| 3 | `test_admin_accesses_publications` | `test_portal_backend_live_integration.py:235` | `None != 200` | Portal server restart |

### Root Cause

Portal uvicorn process was running old code (pre-45.6 commit). After `git checkout main` and cherry-pick, the running server still had the old `main.py` loaded. The new template filters (`fmt_date`) and handler changes (campaign name enrichment, dropdown loading) caused 500 errors on `/campaigns`, `/schedule`, `/publications` — which the live integration tests caught as `status = None` (exception in `_get`).

### Fix

`pkill -f "uvicorn main:app.*8422"` + restart
→ All 3 tests pass. Result: **835 OK (skipped=20)**.

### Classification

| Category | Value |
|----------|-------|
| Domain | Portal live integration (admin RBAC smoke) |
| Demo route related | No (uses real `/campaigns`, `/schedule`, `/publications`) |
| RBAC/RLS related | Indirectly — tests admin role access |
| Security related | No |
| Blocker | Yes (masked real 500 errors from 45.6 changes) |
| Fixed | ✅ Now PASS |

## Backend: 1 Pre-Existing Error (RESOLVED)

| # | Test | File | Error | Resolution |
|---|------|------|-------|------------|
| 1 | `test_client_has_all_methods` | `test_campaign_publication_batch_414.py:492` | `ModuleNotFoundError: No module named 'backend_client'` | Fixed import path |

### Root Cause

Test used relative path `sys.path.insert(0, "apps/portal-web")` — invalid when running from `backend/` directory. Changed to absolute path via `os.path.dirname(__file__)`.

### Fix

```python
# Before:
sys.path.insert(0, "apps/portal-web")
# After:
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "portal-web"))
```

### Classification

| Category | Value |
|----------|-------|
| Domain | Backend test infrastructure |
| Campaign/publication/approval related | Yes (batch lifecycle methods) |
| RBAC/RLS related | No |
| Security related | No |
| Blocker | No (test-only, not production code) |
| Fixed | ✅ Now PASS |

## Summary

| Layer | Before | After |
|-------|--------|-------|
| Portal | 835 tests, 3 failed, 20 skipped | 835 OK, 20 skipped |
| Backend | 770 tests, 1 error | 770 OK |
