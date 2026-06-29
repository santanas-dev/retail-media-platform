-- ═══════════════════════════════════════════════════════════════════════════
-- DEMO DATA CLEANUP DRY-RUN — 45.6.2
-- DO NOT EXECUTE WITHOUT APPROVAL
-- ALL destructive statements are commented out and marked.
-- Run SELECT only to preview candidates.
-- ═══════════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════
-- 1. COUNTS BEFORE
-- ═══════════════════════════════════════════════════════════

SELECT 'users' as entity, count(*) as total FROM users
UNION ALL SELECT 'campaigns', count(*) FROM campaigns
UNION ALL SELECT 'creatives', count(*) FROM creatives
UNION ALL SELECT 'publication_batches', count(*) FROM publication_batches
UNION ALL SELECT 'campaign_creatives', count(*) FROM campaign_creatives
UNION ALL SELECT 'schedules', count(*) FROM schedules
UNION ALL SELECT 'approval_requests', count(*) FROM approval_requests
UNION ALL SELECT 'admin_audit_events', count(*) FROM admin_audit_events
UNION ALL SELECT 'advertisers', count(*) FROM advertisers
ORDER BY entity;

-- ═══════════════════════════════════════════════════════════
-- 2. CREATIVES — JUNK CANDIDATES
-- ═══════════════════════════════════════════════════════════

-- 2a. Draft creatives with junk names (legacy_*, cr-*, test-*)
-- 15 draft total, these are all candidates
SELECT creative_code, name, status,
  CASE WHEN name LIKE 'Test Banner%' THEN 'duplicate_test_banner'
       WHEN name LIKE 'cr-%' THEN 'auto_generated_junk'
       WHEN name LIKE 'test-%' THEN 'test_junk'
       WHEN name LIKE 'legacy_%' AND name NOT IN ('legacy_8ddfc409') THEN 'legacy_draft'
       ELSE 'keep' END as reason
FROM creatives WHERE status = 'draft'
ORDER BY reason, name;

-- 2b. Rejected creatives (2)
-- Both "Test Banner Creative" — junk
SELECT creative_code, name, status FROM creatives WHERE status = 'rejected';

-- 2c. Archived junk creatives (test-creative-seed, Campaign Creative)
SELECT creative_code, name, status FROM creatives
WHERE status = 'archived'
  AND name IN ('Synthetic Creative', 'Campaign Creative');

-- 2d. CREATIVES TO KEEP (for controlled demo dataset):
-- Approved + used: tvorog_e2e, promo_red_30, brand_blue_new, pepsi_promo_jan, tvorog_promo_jan
-- Kept archived (for E2E history): pepsi_e2e (linked to promo_suppliers_e2e)
SELECT creative_code, name, status,
  CASE WHEN creative_code IN ('tvorog_e2e','promo_red_30','brand_blue_new','pepsi_promo_jan','tvorog_promo_jan') THEN 'KEEP_approved'
       WHEN creative_code IN ('pepsi_e2e') THEN 'KEEP_archived_e2e'
       WHEN creative_code = 'legacy_8ddfc409' THEN 'REVIEW_approved_legacy'
       ELSE 'CANDIDATE_DELETE' END as verdict
FROM creatives ORDER BY verdict, name;

-- ═══════════════════════════════════════════════════════════
-- 3. CAMPAIGNS — JUNK CANDIDATES
-- ═══════════════════════════════════════════════════════════

-- 3a. Draft campaigns (16) — ALL junk except possibly none
SELECT campaign_code, name, status,
  CASE WHEN campaign_code = '' OR campaign_code IS NULL THEN 'empty_code'
       WHEN name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C') THEN 'junk_name'
       WHEN name ~ '^C [a-f0-9]' THEN 'auto_name'
       ELSE 'ok' END as reason
FROM campaigns WHERE status = 'draft'
ORDER BY reason, name;

-- 3b. Approved campaigns with empty code (3) — junk
SELECT campaign_code, name, status FROM campaigns
WHERE status = 'approved' AND (campaign_code = '' OR campaign_code IS NULL);

-- 3c. Archived campaigns: test-camp-seed is junk, demo_promo_jan + promo_suppliers_jan are old demo
SELECT campaign_code, name, status,
  CASE WHEN campaign_code = 'test-camp-seed' THEN 'seed_junk'
       WHEN campaign_code IN ('demo_promo_jan','promo_suppliers_jan') THEN 'old_demo_archive'
       WHEN campaign_code = 'promo_suppliers_e2e' THEN 'KEEP_e2e_history'
       ELSE 'unknown' END as verdict
FROM campaigns WHERE status = 'archived';

-- 3d. CAMPAIGNS TO KEEP:
-- promo_suppliers_e2e (archived, E2E history)
-- Maybe 1 fresh draft for active demo
SELECT campaign_code, name, status,
  CASE WHEN campaign_code IN ('promo_suppliers_e2e') THEN 'KEEP'
       WHEN campaign_code IN ('demo_promo_jan','promo_suppliers_jan') THEN 'ARCHIVE_KEEP_OLD_DEMO'
       WHEN campaign_code = 'test-camp-seed' THEN 'CANDIDATE_DELETE'
       WHEN campaign_code = '' OR campaign_code IS NULL THEN 'CANDIDATE_DELETE'
       ELSE 'CANDIDATE_DELETE' END as verdict
FROM campaigns ORDER BY verdict, name;

-- ═══════════════════════════════════════════════════════════
-- 4. USERS — JUNK CANDIDATES
-- ═══════════════════════════════════════════════════════════

-- 4a. Junk users: am-*, an-*, adv*, test-*
SELECT username, display_name,
  CASE WHEN username LIKE 'am-%' THEN 'auto_ad_manager'
       WHEN username LIKE 'an-%' THEN 'auto_analyst'
       WHEN username LIKE 'adv%' THEN 'test_advertiser'
       WHEN username LIKE 'test%' THEN 'test_user'
       WHEN username LIKE 'user%' THEN 'seed_user'
       ELSE 'keep' END as reason
FROM users
WHERE username NOT IN ('admin','creator','approver')
ORDER BY reason, username;

-- 4b. USERS TO KEEP: admin, creator, approver
SELECT username, display_name FROM users
WHERE username IN ('admin','creator','approver');

-- ═══════════════════════════════════════════════════════════
-- 5. PUBLICATION BATCHES — ORPHAN & JUNK
-- ═══════════════════════════════════════════════════════════

-- 5a. All batches linked to junk campaigns (empty name = Test Campaign)
SELECT pb.id, pb.status, c.campaign_code, c.name as camp_name
FROM publication_batches pb JOIN campaigns c ON pb.campaign_id = c.id
WHERE c.campaign_code = '' OR c.campaign_code IS NULL
   OR c.name = 'Test Campaign'
ORDER BY pb.created_at DESC
LIMIT 15;

-- 5b. Count of batches that would be removed
SELECT count(*) as batches_to_delete
FROM publication_batches pb JOIN campaigns c ON pb.campaign_id = c.id
WHERE c.campaign_code = '' OR c.campaign_code IS NULL
   OR c.name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C');

-- 5c. Batches to KEEP (linked to real campaigns)
SELECT pb.id, pb.status, c.campaign_code, c.name
FROM publication_batches pb JOIN campaigns c ON pb.campaign_id = c.id
WHERE c.campaign_code IN ('demo_promo_jan','promo_suppliers_jan','promo_suppliers_e2e','test-camp-seed')
LIMIT 20;

-- ═══════════════════════════════════════════════════════════
-- 6. DEPENDENCY CHECKS
-- ═══════════════════════════════════════════════════════════

-- 6a. campaign_creatives that will be orphaned
SELECT cc.campaign_id, c.campaign_code, c.name, cc.creative_code
FROM campaign_creatives cc JOIN campaigns c ON cc.campaign_id = c.id
WHERE c.campaign_code = '' OR c.campaign_code IS NULL
   OR c.name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C');

-- 6b. Schedules linked to junk campaigns
SELECT s.schedule_code, s.name, s.campaign_code, c.name as camp_name
FROM schedules s LEFT JOIN campaigns c ON s.campaign_code = c.campaign_code
WHERE c.campaign_code IS NULL OR c.campaign_code = ''
   OR c.name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C');

-- ═══════════════════════════════════════════════════════════
-- 7. CONTROLLED DATASET — what remains after cleanup
-- ═══════════════════════════════════════════════════════════

-- 7a. Remaining users (3)
SELECT username, display_name FROM users
WHERE username IN ('admin','creator','approver');

-- 7b. Remaining campaigns (keep archived E2E + old demos, remove junk drafts)
SELECT campaign_code, name, status FROM campaigns
WHERE campaign_code IN ('promo_suppliers_e2e','demo_promo_jan','promo_suppliers_jan');

-- 7c. Remaining creatives (6 approved + pepsi_e2e for history)
SELECT creative_code, name, status FROM creatives
WHERE status = 'approved' OR creative_code = 'pepsi_e2e';

-- ═══════════════════════════════════════════════════════════
-- 8. DESTRUCTIVE QUERIES — DO NOT EXECUTE WITHOUT APPROVAL
-- ═══════════════════════════════════════════════════════════

-- DO NOT EXECUTE WITHOUT APPROVAL
-- BEGIN;
--
-- -- Step 1: Delete orphan campaign_creatives
-- DELETE FROM campaign_creatives
-- WHERE campaign_id IN (SELECT id FROM campaigns WHERE campaign_code='' OR campaign_code IS NULL OR name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C'));
--
-- -- Step 2: Delete junk publication batches
-- DELETE FROM publication_batches
-- WHERE campaign_id IN (SELECT id FROM campaigns WHERE campaign_code='' OR campaign_code IS NULL OR name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C'));
--
-- -- Step 3: Delete junk draft campaigns
-- DELETE FROM campaigns
-- WHERE (campaign_code = '' OR campaign_code IS NULL)
--   AND status = 'draft'
--   AND name IN ('Test Campaign','Booking Campaign','Synthetic Campaign','Test C')
--   AND name ~ '^C [a-f0-9]';
--
-- -- Step 4: Archive seed campaign (don't delete — has creative bindings)
-- UPDATE campaigns SET status = 'archived' WHERE campaign_code = 'test-camp-seed';
--
-- -- Step 5: Delete junk draft creatives (legacy_*, cr-*, test-*)
-- DELETE FROM creatives
-- WHERE status = 'draft'
--   AND creative_code NOT IN (SELECT DISTINCT creative_code FROM campaign_creatives)
--   AND (name LIKE 'Test Banner%' OR name LIKE 'cr-%' OR name LIKE 'test-%');
--
-- -- Step 6: Delete junk users (am-*, an-*, adv*, test*, user*)
-- DELETE FROM users
-- WHERE username NOT IN ('admin','creator','approver')
--   AND (username LIKE 'am-%' OR username LIKE 'an-%' OR username LIKE 'adv%' OR username LIKE 'test%' OR username LIKE 'user%');
--
-- COMMIT;
-- DO NOT EXECUTE WITHOUT APPROVAL
