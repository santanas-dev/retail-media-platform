# Demo Data Cleanup Execution — 45.6.3

**Date:** 2026-06-29  
**Backup:** `backups/backup_retail_media_20260629_115710.dump` (2.2M)  
**DB:** PostgreSQL `retail_media@localhost:5432/retail_media_platform`

## Execution Summary

Three-pass cleanup executed successfully:

### PASS 1: Schedule + Device + Booking + Campaigns
- 15 draft junk campaigns deleted (empty campaign_code)
- schedule_items, schedule_runs, proof_of_play_events **preserved** (linked to C-63939f, kept campaign)
- campaign_bookings, booking_items, campaign_channels, campaign_targets, campaign_renditions cleaned where possible

### PASS 2a: Publication Batch Chain
- 178 device records deleted (device_manifest_requests, device_media_requests, etc.)
- 50 manifest_versions deleted, 19 reassigned to C-63939f batch
- 50 publication_targets deleted, 11 reassigned to C-63939f batch
- 51 publication_batches deleted (linked to draft "Test Campaign")
- 1 remaining draft campaign deleted

### PASS 2b: Creatives + Users
- 11 draft/rejected junk creatives deleted
- 8 orphan creative_versions deleted
- 22 junk users deactivated (is_active=false)
- 32 refresh_tokens deleted

### PASS 3: Remaining Approved Junk
- C-4f099e campaign + children deleted
- "Test Campaign" (approved, empty code) **left in place** — blocked by campaign_renditions referenced by kept manifest_items

## Before vs After

| Table | Before | After | Delta |
|---|---|---|---|
| users (total) | 83 | 83 | 0 |
| users (active) | 74 | 52 | -22 |
| campaigns | 23 | 6 | -17 |
| creatives | 26 | 15 | -11 |
| creative_versions | 23 | 15 | -8 |
| publication_batches | 74 | 23 | -51 |
| publication_targets | 61 | 11 | -50 |
| manifest_versions | 69 | 19 | -50 |
| schedule_items | 25982 | 25982 | 0 |
| proof_of_play_events | 548 | 548 | 0 |
| campaign_bookings | 28 | 28 | 0 |
| booking_items | 27 | 27 | 0 |
| campaign_creatives | 6 | 6 | 0 |
| schedules | 2 | 2 | 0 |
| schedule_slots | 5 | 5 | 0 |
| approval_requests | 1 | 1 | 0 |
| advertisers | 23 | 23 | 0 |
| admin_audit_events | 21 | 21 | 0 |
| refresh_tokens | 1087 | 1055 | -32 |

## Remaining Campaigns (6)

| Name | Status | Note |
|---|---|---|
| C-63939f | approved | KEPT — main demo campaign |
| Test Campaign | approved | JUNK (blocked by renditions) |
| Promo Suppliers E2E Campaign | archived | KEPT — E2E history |
| Synthetic Campaign | archived | JUNK (archived) |
| Промо поставщиков — январь | archived | KEPT — demo history |
| Промо-кампания Январь | archived | KEPT — demo history |

## What Was NOT Done

- Users: **deactivated, not deleted** (is_active=false)
- Admin audit events: **preserved** (21 rows)
- schedule_items / proof_of_play: **preserved** (linked to C-63939f)
- Physical KSO: **not touched**
- Scanner/long-run/sidecar: **not executed**
- Production AV: **not enabled**
- RBAC/RLS/audit: **preserved**
- Tags .0-.6: **not modified**

## Known Residual

- "Test Campaign" (approved, empty code) — 1 campaign_rendition blocks deletion. Low priority, no UI impact.
- "Synthetic Campaign" (archived) — could be deleted but archived is acceptable.

## Rollback

```bash
pg_restore -h localhost -U retail_media -d retail_media_platform \
  --clean --if-exists backups/backup_retail_media_20260629_115710.dump
```
