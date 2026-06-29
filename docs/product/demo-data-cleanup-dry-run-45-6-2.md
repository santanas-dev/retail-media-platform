# Demo Data Cleanup Dry-Run — 45.6.2

## Summary

| Entity | Total | Junk/Seed | Keep | Delete Candidates | Archive Candidates |
|--------|-------|-----------|------|-------------------|-------------------|
| users | 83 | ~80 | 3 (admin, creator, approver) | ~80 | 0 |
| campaigns | 23 | 19 | 1-4 | 16 draft junk | 3 old-demo |
| creatives | 26 | 20 | 6 approved + 1 archived | 17 (draft junk + rejected) | 2 (old seed) |
| publication_batches | 74 | 74 | 0 | 74 | 0 |
| campaign_creatives | 6 | 1 | 5 | 1 (seed link) | 0 |
| schedules | 2 | 0 | 2 | 0 | 0 |
| schedule_slots | 5 | 0 | 5 | 0 | 0 |
| approval_requests | 1 | 0 | 1 (E2E history) | 0 | 0 |
| advertisers | 23 | ~20 | 2-3 | ~20 | 0 |
| admin_audit_events | 21 | 0 | 21 | 0 | 0 |

## Database Inventory (from dry-run queries)

### Users (83)
- **3 real**: admin, creator, approver
- **80 junk**: 20+ `am-*` (auto ad_managers), 20+ `an-*` (auto analysts), test/advertiser seeds

### Creatives (26)
- **6 approved** (usable in campaigns): tvorog_e2e, promo_red_30, brand_blue_new, pepsi_promo_jan, tvorog_promo_jan, legacy_8ddfc409
- **3 archived**: pepsi_e2e (linked to promo_suppliers_e2e), test-creative-seed (seed), legacy_ae8a928f (Campaign Creative)
- **15 draft junk**: legacy_* (Test Banner Creative × 5), cr-* (auto-named × 10), test-*
- **2 rejected**: Test Banner Creative (duplicates)

### Campaigns (23)
- **16 draft** — ALL junk: empty campaign_code, names like "Test Campaign", "Booking Campaign", "C xxxxx"
- **3 approved** — ALL with empty campaign_code (C-4f099e, C-63939f, Test Campaign)
- **4 archived**:
  - `promo_suppliers_e2e` — KEEP (E2E history)
  - `demo_promo_jan` — old demo, archive/keep for reference
  - `promo_suppliers_jan` — old demo, archive/keep for reference
  - `test-camp-seed` — seed junk, archive or delete

### Publication Batches (74)
- ALL linked to "Test Campaign" (empty-code campaigns)
- 39 published, 25 draft, 7 cancelled, 3 generated
- 0 orphans (all have valid campaign_id FK)
- **Verdict**: all 74 are junk — delete after removing parent campaigns

### Campaign Creatives (6)
- `promo_suppliers_e2e` ← pepsi_e2e, tvorog_e2e (KEEP)
- `promo_suppliers_jan` ← pepsi_promo_jan (KEEP)
- `demo_promo_jan` ← promo_red_30, brand_blue_new (KEEP)
- `test-camp-seed` ← test-creative-seed (CANDIDATE_DELETE)

### Schedules (2)
- `demo_schedule_jan` → campaign demo_promo_jan (KEEP)
- `sched_promo_suppliers_e2e` → campaign promo_suppliers_e2e (KEEP)
- 5 schedule slots total

### Roles (8)
- system_admin, ad_manager, approver, advertiser, analyst, device_service, operations, security_admin
- All KEEP

## Controlled Demo Dataset (Target)

| Entity | Count | Items |
|--------|-------|-------|
| Users | 3 | admin (system_admin), creator (ad_manager), approver (approver) |
| Campaigns | 1-4 | promo_suppliers_e2e (archived history), demo_promo_jan, promo_suppliers_jan, + 1 fresh draft |
| Creatives | 5-7 | 6 approved + pepsi_e2e (E2E history) |
| Publication batches | 0-1 | New batch for fresh campaign |
| Schedules | 2 | demo_schedule_jan, sched_promo_suppliers_e2e |
| Approval requests | 1 | promo_suppliers_e2e approval |
| Audit events | 21 | Preserved |

## Dependency Graph

```
campaign ──┬── campaign_creatives ─── creatives
           ├── schedules ─── schedule_slots
           ├── publication_batches
           └── approval_requests

users ──── created_by (campaigns/creatives/batches)
```

### Risks
- **Delete campaign → cascade**: Must delete campaign_creatives and publication_batches first (FK RESTRICT)
- **Delete creatives → cascade**: Must unlink from campaign_creatives first
- **Delete users → audit trail**: users referenced in created_by/approved_by fields. These should be SET NULL or the users should be deactivated (is_active=false) instead of deleted
- **No orphan risk**: All batches have valid campaign_id FKs (verified: 0 orphans)

## Backup Plan

### Before Cleanup
```bash
# 1. Full DB backup
pg_dump -h localhost -U retail_media -d retail_media_platform \
  -Fc -f backup_retail_media_$(date +%Y%m%d_%H%M%S).dump

# 2. Export affected rows for rollback
psql -h localhost -U retail_media -d retail_media_platform -c "
  COPY (SELECT * FROM campaigns WHERE campaign_code='' OR campaign_code IS NULL) TO '/tmp/backup_campaigns.csv' CSV HEADER;
  COPY (SELECT * FROM publication_batches pb JOIN campaigns c ON pb.campaign_id=c.id WHERE c.campaign_code='' OR c.campaign_code IS NULL) TO '/tmp/backup_batches.csv' CSV HEADER;
  COPY (SELECT * FROM creatives WHERE status='draft' AND creative_code NOT IN (SELECT DISTINCT creative_code FROM campaign_creatives)) TO '/tmp/backup_creatives.csv' CSV HEADER;
"
```

### Rollback
```bash
pg_restore -h localhost -U retail_media -d retail_media_platform \
  --clean --if-exists backup_retail_media_YYYYMMDD.dump
```

### Verification After Cleanup
1. `python3 -m unittest discover -s apps/portal-web/tests -v` → 835 OK
2. `python3 -m unittest discover -s backend/tests -v` → 770 OK
3. Login as creator, approver, admin
4. Visible action click audit
5. Campaign assembly with approved creatives
6. Maker-checker flow

## Controlled Dataset Verification Plan

| Step | Action | Expected |
|------|--------|----------|
| 1 | Login creator | 200, dashboard |
| 2 | Login approver | 200, dashboard |
| 3 | Login admin | 200, /admin |
| 4 | Campaign list | Only kept campaigns visible |
| 5 | Creative list | Only kept creatives visible |
| 6 | Create fresh campaign | creator can create |
| 7 | Add 2-3 approved creatives | Dropdown has kept creatives |
| 8 | Create 2 placements (schedule) | Dropdown has kept campaigns |
| 9 | Add 5 Mon-Fri slots | Slots created |
| 10 | Submit for approval | Status in_review |
| 11 | Approver approves | Status approved |
| 12 | Prepare publication batch | Batch created |
| 13 | Reports show planned placements | No errors |
| 14 | Click audit | All actions work |
| 15 | No raw JSON | 0 occurrences |
| 16 | No tech terms visible | 0 |
| 17 | No seed/test visible | 0 |
| 18 | RBAC/RLS/audit preserved | All enforced |
