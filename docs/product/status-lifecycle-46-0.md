# Status Lifecycle Cleanup — 46.0

**Date:** 2026-06-29
**Baseline:** 24dfa93

## Status Inventory

| Entity | Statuses | Final? |
|---|---|---|
| Campaign | draft → in_review → approved / rejected → archived | Yes (archived) |
| Creative | draft → uploaded → pending → approved / rejected / return_for_rework → archived | Yes (archived) |
| ApprovalRequest | pending → approved / rejected | Yes (both) |
| Schedule | draft → active → archived | Yes (archived) |
| ScheduleSlot | active / disabled | No |
| PublicationBatch | draft → pending_approval → approved → manifest_generated → published / cancelled / rejected / failed | Yes (published, cancelled, rejected, failed) |
| PublicationTarget | pending → generated → published / failed / cancelled | Yes |
| ManifestVersion | draft → approved → published / cancelled | Yes |

## Changes

### Portal Status Labels
- campaigns_detail.html: `{{ campaign.status \| sanitize }}` → Russian dict lookup
- schedule.html: `{{ s.status }}` → Russian dict lookup
- publications.html: manifest `{{ m.status \| sanitize }}` → Russian dict lookup
- All creative statuses, scan_status added to Russian labels

### Publication Dead-End Guidance
- publications.html: cancelled/rejected batches now show "Действие завершено" with next-step guidance

### CSS Restoration
- Re-added 30+ utility classes removed by aggressive purge: btn variants, status badges, spacing, text utilities, panels

### Tests
- 18 status lifecycle tests: campaign, approval, publication, schedule, portal labels, API schema, raw status visibility

## Regression
- Backend: 804 passed (0 files changed)
- Portal: 831 passed, 32 skipped (+18 tests)
