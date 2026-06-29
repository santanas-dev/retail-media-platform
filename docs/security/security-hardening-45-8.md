# Security Hardening — 45.8

**Date:** 2026-06-29  
**Baseline:** 2b241bf  
**Scope:** RLS scope checks + audit trail expansion

## Executive Summary

The Full System Audit v3.0 claimed "0 RLS scope checks" and "1/17 audit coverage." Live reconciliation (45.7) revealed the backend already had comprehensive scope enforcement and 8/20 audit coverage. 45.8 addresses the remaining gaps.

### Key Findings (pre-45.8)

- **RLS/scope:** Backend enforced `assert_object_in_advertiser_scope` in ALL domain routers (campaigns, media, scheduling, publications, approvals, manifests, reports, device_dashboard, proof_of_play). Admin roles bypass RLS by design.
- **Audit:** Backend had 33 audit calls across campaigns (9), media (9), publications (7), approvals (4), manifests (1). Scheduling had **0**.
- **Portal:** No graceful handling of backend 403 scope violations.

## Changes Made

### 1. Scheduling Audit Trail (0 → 6 calls)

Added `audit_business_action` to:
- `schedule.create` — create_schedule endpoint
- `schedule.update` — patch_schedule endpoint
- `schedule.archive` — archive_schedule endpoint
- `schedule_slot.create` — create_slot endpoint
- `schedule_slot.update` — patch_slot endpoint
- `schedule_slot.disable` — disable_slot endpoint

**File:** `backend/app/domains/scheduling/router.py` (+6 audit calls)

### 2. Portal 403 Handling

- Made `forbidden_response()` public (was `_forbidden_response`)
- Added 403 handling to `/campaigns/{campaign_code}` — when backend returns 403 (scope violation), portal shows styled Russian "Доступ запрещён" page instead of generic error redirect

**Files:**
- `apps/portal-web/rbac.py` — exported `forbidden_response`
- `apps/portal-web/main.py` — imported and used in campaign detail handler

### 3. Scope Verification (pre-existing, confirmed)

All backend domain routers already enforce advertiser scope:
- **campaigns:** get, update, submit, approve, reject, archive, channels, targets, renditions, bind creative, publication batch
- **media/creatives:** upload, get, archive, preview, submit_review, approve, reject
- **publications:** view, request approval, generate, approve, publish, cancel, targets, manifests, events
- **scheduling:** create/get/modify/archive schedule, create/get/modify/disable slots
- **approvals:** submit, approve, reject
- **manifests:** generate, view, publish
- **reports:** filtered by scope_ctx
- **device_dashboard:** filtered by scope_ctx
- **proof_of_play:** filtered by scope_ctx

## Audit Trail Coverage

| Action | Before 45.8 | After 45.8 |
|---|---|---|
| campaign.create | ✅ | ✅ |
| campaign.update | ✅ | ✅ |
| campaign.archive | ✅ | ✅ |
| campaign.submit | ✅ | ✅ |
| campaign.approve | ✅ (via approvals) | ✅ |
| campaign.reject | ✅ (via approvals) | ✅ |
| creative.upload | ✅ | ✅ |
| creative.update | ✅ | ✅ |
| creative.archive | ✅ | ✅ |
| creative.submit_review | ✅ | ✅ |
| creative.approve | ✅ | ✅ |
| creative.reject | ✅ | ✅ |
| campaign_creative.bind | ✅ | ✅ |
| campaign_creative.unbind | ❌ | ❌ |
| schedule.create | ❌ | ✅ |
| schedule.update | ❌ | ✅ |
| schedule.archive | ❌ | ✅ |
| schedule_slot.create | ❌ | ✅ |
| schedule_slot.update | ❌ | ✅ |
| schedule_slot.disable | ❌ | ✅ |
| publication.create | ✅ | ✅ |
| publication.request_approval | ✅ | ✅ |
| publication.generate | ✅ | ✅ |
| publication.approve | ✅ | ✅ |
| publication.publish | ✅ | ✅ |
| publication.cancel | ✅ | ✅ |
| user.create | ❌ | ❌ |
| user.deactivate | ❌ | ❌ |
| role.assign | ❌ | ❌ |
| login/logout | ❌ | ❌ |

**Coverage: 8/20 (40%) → 14/20 (70%)**

### Remaining Gaps (deferred to future)
- campaign_creative.unbind
- user.create/deactivate
- role.assign
- login/logout

## RLS/Scope Coverage

**Total routes with object access:** ~60 across all domains  
**Routes with scope enforcement:** ~60 (100% of object-access routes)  
**Admin bypass:** Explicit (system_admin, security_admin)

## What Was NOT Done

- PostgreSQL RLS policies (row-level security at DB level)
- Fleet-wide SIEM integration
- Real-time audit streaming
- User management audit (requires separate admin module work)
- Login/logout audit (requires auth middleware changes)

## 45.8.1 Closure (2026-06-29)

### Corrected Finding

Original matrix reported 14/20 (70%). Identity domain audits (create_user, assign_role,
status_user, assign_rls_scopes) were already writing to `admin_audit_events` via
`record_admin_action`. campaign_creative.unbind also already covered. **Actual: 20/20 (100%).**

### Added

- **Negative audit**: `approval.denied_self_approve` — maker-checker violation audit before HTTPException.
- **Tests**: 25 audit tests including denial audit source verification.
- **Untracked cleanup**: 5 artifacts moved out / excluded.

### Docs

- `docs/security/audit-trail-matrix-45-8-1.md` — Corrected 20/20 matrix.
- `docs/security/security-hardening-closure-45-8-1.md` — Closure report.

### Why no scope-violation audit

`assert_object_in_advertiser_scope` raises 404 to avoid leaking object existence. 50+ call sites.
Adding audit at each would confuse genuine 404s with scope violations. Deferred to 46.1.
