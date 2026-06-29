-- ============================================================================
-- KSO Data Migration Dry-Run SQL — A.3
-- READ-ONLY. No INSERT/UPDATE/DELETE/DROP.
-- Запускать перед реальной миграцией для проверки.
-- ============================================================================

-- 1. INVENTORY: Counts
SELECT '=== KSO LEGACY COUNTS ===' as step;
SELECT 'kso_devices' as tbl, COUNT(*) as rows FROM kso_devices
UNION ALL SELECT 'kso_placements', COUNT(*) FROM kso_placements
UNION ALL SELECT 'kso_proof_of_play_events', COUNT(*) FROM kso_proof_of_play_events;

SELECT '=== UNIVERSAL COUNTS ===' as step;
SELECT 'channels' as tbl, COUNT(*) as rows FROM channels
UNION ALL SELECT 'device_types', COUNT(*) FROM device_types
UNION ALL SELECT 'capability_profiles', COUNT(*) FROM capability_profiles
UNION ALL SELECT 'physical_devices', COUNT(*) FROM physical_devices
UNION ALL SELECT 'logical_carriers', COUNT(*) FROM logical_carriers
UNION ALL SELECT 'display_surfaces', COUNT(*) FROM display_surfaces
UNION ALL SELECT 'manifest_versions', COUNT(*) FROM manifest_versions;

-- 2. ORPHAN CHECKS
SELECT '=== ORPHAN: PoP device_code not in kso_devices ===' as step;
SELECT kp.event_code, kp.device_code
FROM kso_proof_of_play_events kp
LEFT JOIN kso_devices kd ON kd.device_code = kp.device_code
WHERE kd.id IS NULL;

SELECT '=== ORPHAN: PoP campaign_code not in campaigns ===' as step;
SELECT kp.event_code, kp.campaign_code
FROM kso_proof_of_play_events kp
LEFT JOIN campaigns c ON c.campaign_code = kp.campaign_code
WHERE c.id IS NULL;

SELECT '=== ORPHAN: PoP manifest_code not in manifest_versions ===' as step;
SELECT kp.event_code, kp.manifest_code
FROM kso_proof_of_play_events kp
LEFT JOIN manifest_versions mv ON mv.manifest_code = kp.manifest_code
WHERE mv.id IS NULL;

SELECT '=== ORPHAN: PoP creative_code not in creatives ===' as step;
SELECT kp.event_code, kp.creative_code
FROM kso_proof_of_play_events kp
LEFT JOIN creatives cr ON cr.creative_code = kp.creative_code
WHERE cr.id IS NULL;

-- 3. DUPLICATE CHECKS
SELECT '=== DUPLICATE: kso_devices.device_code ===' as step;
SELECT device_code, COUNT(*) as cnt FROM kso_devices
GROUP BY device_code HAVING COUNT(*) > 1;

SELECT '=== DUPLICATE: kso_placements.placement_code ===' as step;
SELECT placement_code, COUNT(*) as cnt FROM kso_placements
GROUP BY placement_code HAVING COUNT(*) > 1;

-- 4. DRY-RUN: kso_devices → physical_devices preview
SELECT '=== DRY-RUN: kso_devices → physical_devices ===' as step;
SELECT 
    kd.device_code AS would_be_external_code,
    kd.store_id,
    dt.code AS would_match_device_type,
    CASE kd.status WHEN 'active' THEN 'online' ELSE 'offline' END AS would_be_status,
    kd.display_name,
    kd.screen_width, kd.screen_height
FROM kso_devices kd
JOIN device_types dt ON dt.code = 'kso_gen5';

-- 5. DRY-RUN: kso_placements → placements preview
SELECT '=== DRY-RUN: kso_placements → placements ===' as step;
SELECT 
    kp.placement_code AS would_be_code,
    c.campaign_code,
    c.name AS campaign_name,
    kp.status,
    kp.starts_at::date AS would_be_start_date,
    kp.ends_at::date AS would_be_end_date
FROM kso_placements kp
JOIN campaigns c ON c.campaign_code = kp.campaign_code;

-- 6. DRY-RUN: placement_targets preview  
SELECT '=== DRY-RUN: placement_targets ===' as step;
SELECT
    kp.placement_code,
    'store' AS would_be_target_type,
    s.name AS store_name,
    kp.device_code
FROM kso_placements kp
JOIN kso_devices kd ON kd.device_code = kp.device_code
JOIN stores s ON s.id = kd.store_id;

-- 7. DRY-RUN: kso_proof_of_play_events → proof_events preview
SELECT '=== DRY-RUN: kso_pop → proof_events ===' as step;
SELECT 
    kp.event_code,
    'real_playback' AS would_be_proof_type,
    kp.device_code AS would_join_via_external_code,
    kp.campaign_code,
    kp.creative_code,
    kp.manifest_code,
    kp.played_at AS would_be_started_at,
    kp.duration_ms,
    CASE kp.event_type WHEN 'test_playback_completed' THEN 'success' ELSE kp.event_type END AS would_be_playback_result,
    'KSO' AS would_be_channel_type
FROM kso_proof_of_play_events kp;

-- 8. NULL FIELD CHECKS
SELECT '=== NULL: kso_devices critical fields ===' as step;
SELECT 
    COUNT(*) FILTER (WHERE device_code IS NULL) AS null_device_code,
    COUNT(*) FILTER (WHERE store_id IS NULL) AS null_store_id
FROM kso_devices;

SELECT '=== NULL: kso_placements critical fields ===' as step;
SELECT 
    COUNT(*) FILTER (WHERE placement_code IS NULL) AS null_placement_code,
    COUNT(*) FILTER (WHERE campaign_code IS NULL) AS null_campaign_code
FROM kso_placements;

-- 9. EXISTING physical_devices check (any conflicting external_code?)
SELECT '=== CONFLICT: existing external_code in physical_devices ===' as step;
SELECT pd.id, pd.external_code
FROM physical_devices pd
WHERE pd.external_code IN (SELECT device_code FROM kso_devices);

-- ============================================================================
-- END DRY-RUN. No data modified.
-- ============================================================================
