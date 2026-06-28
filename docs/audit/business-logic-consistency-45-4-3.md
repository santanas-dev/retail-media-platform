# Business Logic Consistency Fix — 45.4.3

**Date:** 2026-06-26  
**Branch:** main  
**Baseline:** 5c30651 (45.4.2 — business demo cleanup)

## Problem

After 45.4.2 visual polish, the portal UI looked ready, but underlying data inconsistencies between backend state machine and portal KPI/counters made business demo unreliable.

## Canonical Status Machine

### Campaign lifecycle (backend → portal)
```
draft → in_review → approved / rejected → archived
```
- Backend writes: `draft`, `in_review`, `approved`, `rejected`, `archived`
- Portal **was** counting `pending_approval` (never written) → always 0
- **Fixed**: portal now uses `in_review` everywhere

### Approval object lifecycle
```
pending → approved / rejected
```
- Separate entity from campaign.status
- NOT affected by this fix

### Publication batch lifecycle
```
draft → pending_approval → approved → manifest_generated → published / cancelled
```
- `pending_approval` IS valid here — separate from campaign status

### Schedule lifecycle
```
draft → archived
```
- Portal was counting `active` (never written) — removed

### Manifest lifecycle
```
generated → published
```
- Portal was counting `draft` (never written) → changed to `generated`

## Fixes Applied

### P0.1 — `in_review` / `pending_approval` mismatch

| File | Change |
|------|--------|
| `main.py:167` | `pending_campaigns` counts `in_review` not `pending_approval` |
| `main.py:1502` | `status_counts` key `in_review` (was `pending_approval`) |
| `main.py:1465` | `_status_label("in_review")` → «На согласовании» (was «На проверке») |
| `campaigns.html:59` | `campaigns_by_status.in_review` (was `.pending_approval`) |
| `campaigns.html:92` | `c.status == 'in_review'` with `status-badge-in_review` |
| `sanitizer.py:55` | Added `"in_review": "На согласовании"` |

### P0.2 — KPI/status counters

| Counter | Before | After |
|---------|--------|-------|
| `active_schedules` | Always 0 (status never written) | Removed |
| `archived_schedules` | Missing | Added |
| `draft_manifests` | Always 0 (manifests don't use `draft`) | Renamed to `generated_manifests` |

### P0.3 — Campaign readiness gap

**Confirmed:** Backend `_check_campaign_ready()` requires:
1. At least 1 channel (`campaign_channels`)
2. At least 1 target (`campaign_targets`)
3. At least 1 active, valid rendition with approved creative

**Portal gap:** No UI for managing channels, targets, renditions on campaigns.  
**Impact:** Campaign `submit` will fail for campaigns without these pre-seeded.  
**Status:** P1 product gap — documented, not blocking demo if pre-seeded campaigns used.

### P0.4 — Multi-creative campaign model

**Confirmed ✅:** Campaign model supports multiple creatives via `campaign_creatives` table (many-to-many). Portal's `bind-creative` endpoint adds one creative at a time.

## Tests

| Layer | Result |
|-------|--------|
| Portal regression | **756** passed, 0 failed |
| Backend regression | **807** passed, 0 failed |
| Pre-existing test fixes | 2 (`in_review` in campaign status validation) |

## Manual Scenario

PENDING — requires portal with live backend to verify complete flow:  
creatives → campaign → placements → approval → publication → reports.

Current blocker: campaign readiness gap (channels/targets/renditions) may prevent submit for newly created campaigns.

## Remaining Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| Channels/targets/renditions UI | P1 | Submit fails without these |
| Multi-creative UI binding in single view | P2 | Portal binds one at a time |
| Schedule "active" count | P2 | No such status in backend |
| Manual scenario E2E verification | P1 | Requires pre-seeded data or gap fix |
