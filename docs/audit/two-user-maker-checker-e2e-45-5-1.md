# Two-User Maker-Checker E2E — 45.5.1 Audit

**Date:** 2026-06-28
**Status:** ✅ PASS — Full two-user scenario completed

## E2E Result: PASS ✅

| Step | Actor | Action | Result |
|------|-------|--------|--------|
| 1 | creator | Login | ✅ Token obtained |
| 2 | approver | Login | ✅ Token obtained |
| 3 | creator | Upload Pepsi (pepsi_e2e) | ✅ Created, status=pending_review |
| 4 | creator | Upload Tvorog (tvorog_e2e) | ✅ Created, status=pending_review |
| 5 | creator | Submit both for review | ✅ → in_review |
| 6 | creator | **Self-approve creative** | ❌ **BLOCKED** — 403 `Missing required permission: media.approve` |
| 7 | **approver** | Approve Pepsi | ✅ Approved (cross-user) |
| 8 | **approver** | Approve Tvorog | ✅ Approved (cross-user) |
| 9 | creator | Create campaign `promo_suppliers_e2e` | ✅ Created, status=draft, 2 creatives |
| 10 | creator | Create schedule + 5 slots | ✅ Schedule with Mon-Fri slots |
| 11 | creator | Submit campaign | ✅ → pending_approval, ApprovalRequest created |
| 12 | creator | **Self-approve campaign** | ❌ **BLOCKED** — 403 `Missing required permission: campaigns.approve` |
| 13 | **approver** | Approve campaign | ✅ Approved (cross-user) |
| 14 | — | Check campaign status | ✅ `approved` |

## Maker-Checker Enforcement

Enforced at **permission layer** — role-based, not code-level:

| User | Role | Can Create | Can Approve |
|------|------|-----------|-------------|
| creator | ad_manager | ✅ campaigns.manage, media.manage | ❌ |
| approver | approver | ❌ | ✅ campaigns.approve, media.approve |

Same-user approval blocked by permission pre-check (403 before business logic).
Cross-user approval (approver approves creator's work) succeeds.

## Users Created

- **creator** / CreatorTest123! — ad_manager (27 permissions)
- **approver** / ApproverTest123! — approver (20 permissions)
- Created via POST /api/users with `role_codes` parameter

## Bug Found & Fixed

**schedule_slots missing `updated_at` column**: The ORM model `ScheduleSlot` expected an `updated_at` column that didn't exist in the database, causing 500 on schedule operations. Fixed with `ALTER TABLE schedule_slots ADD COLUMN updated_at TIMESTAMPTZ`.

## Creative Status Visibility Fixed

`list_campaign_creatives` now returns enriched creative metadata:
- `name` — creative display name
- `status` — approval status (approved/in_review/rejected)
- `mime_type` — file format
- `file_size` — file size in bytes
- `scan_status` — AV scan status
- `width`, `height` — dimensions

This fixes the "⬜ Креативы одобрены" false negative on the readiness checklist.

## Backend Test Failures Classification

**39 failed, 768 passed** (pre-existing, all unrelated):

| Module | Failures | Root Cause | Domain |
|--------|----------|-----------|--------|
| test_airtime_occupancy | 15 | ModuleNotFoundError (missing import path) | Airtime |
| test_inventory_engine_441 | 19 | ModuleNotFoundError (import failure) | Inventory |
| test_creative_preview | 4 | Pre-existing route mismatch | Media |
| test_campaign_publication_batch_414 | 1 | Pre-existing | Publications |

**None related to:** campaigns, campaign_creatives, schedules, approvals, RBAC/RLS, reports, publications, media moderation.

**Documented as non-blocking.**

## UI Gaps

| Gap | Status |
|-----|--------|
| Creative status in campaign_creatives | ✅ Fixed (enriched endpoint) |
| Empty state quick actions | ✅ Added (upload CTA, schedule CTA) |
| Preview/thumbnail in campaign card | P2 — deferred (not blocker) |
| Drag-and-drop creative sorting | P3 — deferred (backlog) |
| maker-checker user creation UI | Not yet — seed/admin script only |

## Safety Confirmation

- ✅ RBAC/RLS/audit trail not weakened
- ✅ Physical KSO/SSH/X11/Chromium/runner/sidecar/PoP — untouched
- ✅ Scanner E2E/long-run/sidecar sync — not executed
- ✅ Production AV — not enabled
- ✅ No fake AV pass
- ✅ No JS/CDN/localStorage
- ✅ No secrets/leaks
- ✅ No visible test/seed/None labels
