# Demo Data Cleanup Plan — 45.6.1

## Current State (PostgreSQL)

| Entity | Count | Notes |
|--------|-------|-------|
| campaigns | 23 | 16 draft (junk: "Test Campaign", "C-xxxx"), 3 approved, 4 archived |
| creatives | 26 | Mostly seed, various statuses |
| publication_batches | 74 | Mostly seed batches tied to old campaigns |
| schedules | 2 | Linked to test campaigns |
| approval_requests | 1 | Single test approval |
| campaign_creatives | 6 | Bindings between seed campaigns and creatives |
| users | 83 | Many seed/test users |
| advertisers | 23 | Seed advertisers |

## Problems

1. **Empty campaign_code** — campaigns without code (shown as empty in UI)
2. **Junk names** — "C-xxxx", "Test Campaign", "Booking Campaign"
3. **Seed test data** — Synthetic Campaign, test-camp-seed
4. **74 publication batches** — from old seed data
5. **83 users** — far more than needed

## Cleanup Approach

### Phase 1: Identify Controlled Dataset

Keep:
- `creator` user (ad_manager role)
- `approver` user (approver role)  
- `admin` user (system_admin role)
- Campaign: `promo_suppliers_e2e` or create fresh one
- 2-3 creatives (approved, with preview)
- 2 placements (schedules)
- 1 publication batch
- 1 approval request

### Phase 2: Dry-Run Preview Queries

```sql
-- Candidates for deletion (draft junk campaigns)
SELECT campaign_code, name, status, created_at
FROM campaigns
WHERE campaign_code = '' OR campaign_code IS NULL
   OR name IN ('Test Campaign', 'Booking Campaign', 'Synthetic Campaign', 'Test C')
   OR campaign_code LIKE 'C %'
   OR campaign_code LIKE 'C-%' AND name LIKE 'C %'
ORDER BY created_at;

-- Publication batches linked to junk campaigns
SELECT pb.id, pb.campaign_code, pb.status
FROM publication_batches pb
LEFT JOIN campaigns c ON pb.campaign_code = c.campaign_code
WHERE c.campaign_code IS NULL OR c.status = 'draft';

-- Unused creatives (not linked to any campaign)
SELECT cr.creative_code, cr.name, cr.status
FROM creatives cr
LEFT JOIN campaign_creatives cc ON cr.creative_code = cc.creative_code
WHERE cc.creative_code IS NULL;
```

### Phase 3: Safe Cleanup (dry-run first)

1. **Export** — `pg_dump retail_media_platform > backup_$(date +%Y%m%d).sql`
2. **Dry-run** — Run DELETE with RETURNING to see what will be removed
3. **Execute** — Only after review of dry-run output
4. **Verify** — Portal regression, E2E test

### Phase 4: Reset to Controlled Dataset

```sql
-- WARNING: Dry-run first. Review output before executing.

BEGIN;

-- 1. Remove junk campaign-creative bindings
DELETE FROM campaign_creatives
WHERE campaign_code IN (
  SELECT campaign_code FROM campaigns
  WHERE campaign_code = '' OR campaign_code IS NULL
     OR name IN ('Test Campaign', 'Booking Campaign', 'Synthetic Campaign', 'Test C')
     OR (campaign_code LIKE 'C %' AND name LIKE 'C %')
);

-- 2. Remove junk publication batches
DELETE FROM publication_batches
WHERE campaign_code IN (
  SELECT campaign_code FROM campaigns
  WHERE campaign_code = '' OR campaign_code IS NULL
     OR name IN ('Test Campaign', 'Booking Campaign', 'Synthetic Campaign', 'Test C')
     OR (campaign_code LIKE 'C %' AND name LIKE 'C %')
)
OR campaign_code NOT IN (SELECT campaign_code FROM campaigns);

-- 3. Archive (don't delete) old campaigns
UPDATE campaigns SET status = 'archived'
WHERE campaign_code IN ('test-camp-seed', 'demo_promo_jan')
   OR (campaign_code LIKE 'C %' AND name LIKE 'C %' AND status = 'draft');

-- 4. Remove orphaned creatives
DELETE FROM creatives
WHERE creative_code NOT IN (
  SELECT DISTINCT creative_code FROM campaign_creatives
)
AND status = 'draft';

-- 5. Remove seed advertisers (keep if linked)
DELETE FROM advertisers
WHERE advertiser_code NOT IN (
  SELECT DISTINCT advertiser_code FROM campaigns WHERE advertiser_code IS NOT NULL
)
AND name LIKE 'Test%' OR name LIKE 'Seed%';

-- 6. Remove seed users (keep creator, approver, admin)
DELETE FROM users
WHERE username NOT IN ('creator', 'approver', 'admin')
AND (username LIKE 'test%' OR username LIKE 'seed%' OR username LIKE 'user%');

COMMIT;
```

### Controlled Dataset Target

| Entity | Count | Description |
|--------|-------|-------------|
| Users | 3 | creator (ad_manager), approver (approver), admin (system_admin) |
| Campaigns | 1-2 | Promo Suppliers E2E (archived) + 1 fresh draft |
| Creatives | 2-3 | Approved creatives with preview |
| Placements | 2 | Linked to campaign |
| Publication batches | 1 | Linked to approved campaign |
| Approval requests | 1 | Pending or decided |

### Safety Rules

- **Never** DELETE without dry-run first
- **Always** pg_dump backup before any DELETE
- **Never** delete `creator`, `approver`, `admin` users
- **Never** delete creatives with `status = 'approved'` that have campaign bindings
- Audit trail remains intact — don't touch `admin_audit_events`
- Don't touch `device_*`, `gateway_*`, `capability_*`, `channels`, `branches`, `brands`

### Post-Cleanup Verification

```bash
# After cleanup:
python3 -m unittest discover -s apps/portal-web/tests -v
python3 -m unittest discover -s backend/tests -v

# Click audit: all visible actions
# Two-user E2E: creator → approver → prepare → publish
```
