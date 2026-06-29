# Security Hardening Closure — 45.8.1

**Date:** 2026-06-29
**Parent:** 45.8 (commit `8589f8b`)
**Status:** COMPLETE

## Executive Summary

45.8.1 closes the remaining items from 45.8 security hardening:

1. **False positive corrected**: The original 45.8 matrix reported 14/20 (70%) audit coverage.
   Audit of all 7 domains revealed identity domain audits (create_user, assign_role, status_user,
   assign_rls_scopes) were already writing to `admin_audit_events` via `record_admin_action` —
   the same table as `audit_business_action`. campaign_creative.unbind was also already covered.
   **Actual coverage: 20/20 (100%)**.

2. **Negative audit added**: Self-approve denial (`approval.denied_self_approve`) is now audited
   before the HTTPException is raised. This captures maker-checker violations.

3. **Untracked artifacts**: 5 items (backups, QA reports, transient docs) moved out of repo
   or added to `.git/info/exclude`.

## Changes

### Code
| File | Change |
|---|---|
| `backend/app/domains/approvals/service.py` | +7 lines: audit before self-approve denial |
| `backend/tests/test_audit_hardening.py` | +78 lines: denial audit tests, action name tests |

### Docs
| File | Change |
|---|---|
| `docs/security/audit-trail-matrix-45-8-1.md` | Corrected 20/20 matrix |
| `docs/security/security-hardening-closure-45-8-1.md` | This file |

## Audit Coverage

| Metric | 45.8 (reported) | 45.8 (actual) | 45.8.1 |
|---|---|---|---|
| Business actions | 14/20 (70%) | 20/20 (100%) | 20/20 (100%) |
| Negative audit | 0 | 0 | 1 |
| Login audit | separate table | separate table | unchanged |
| Total admin_audit_events actions | 14 | 34 | 35 (+N1) |

## Tests

| Suite | Result |
|---|---|
| test_audit_hardening.py | 25/25 passed |
| Backend regression (excl. pre-existing import errors) | 804 passed, 0 failed |
| Portal regression | 803 passed, 32 skipped |

## Security Gates

| Gate | Status |
|---|---|
| RLS/scope enforcement | 66 assert calls, 47 routes ✅ |
| Maker-checker | enforced + audited ✅ |
| RBAC | unchanged, all tests pass ✅ |
| Cross-advertiser isolation | 23/23 tests pass ✅ |
| Raw JSON in portal | 0 ✅ |
| JS/CDN/localStorage | 0 ✅ |
| Secrets in templates | login form labels only (safe) ✅ |
| Physical KSO | 0 files touched ✅ |
| Scanner/long-run/sidecar | not executed ✅ |
| Production AV | not enabled ✅ |

## Why no scope-violation audit

`assert_object_in_advertiser_scope` raises 404 (not 403) to avoid leaking object existence.
Called from 50+ sites across 6 routers. Adding audit at each call site would be noisy and
confuse genuine 404s with scope violations. Deferred to post-pilot phase when 403/404
separation can be done with a dedicated security middleware.

## Remaining Gaps (non-blocking)

None. All 20 target actions covered + 1 negative audit.
Deferred to 46.1 (compliance): login/logout in admin_audit_events, scope-violation audit middleware.
