# KSO Data Migration Plan — A.3

> **Дата:** 2026-06-29 | **Этап:** A.3 (EXECUTED ✅)  
> **Статус:** ВЫПОЛНЕН — commit `cb7f294` | Safety Gate: A.3.2 ✅  
> **Основание:** ERD v2.5 (A.2), KSO Duplicate Mapping (A.2)

---

## 1. Inventory Summary (read-only, 2026-06-29)

### KSO Legacy Tables

| Таблица | Строк | Статус | FK зависимости |
|---|---|---|---|
| `kso_devices` | 1 | ✅ active | store_id → stores |
| `kso_placements` | 1 | ✅ active | campaign_code, device_code |
| `kso_proof_of_play_events` | 2 | ✅ accepted | campaign_code, device_code, etc. |

### Universal v2.5 Tables

| Таблица | Строк | Статус | Примечание |
|---|---|---|---|
| `channels` | 1 | `kso_gen5` | ⚠️ Seed определяет 5, в БД только 1 |
| `device_types` | 1 | `kso_gen5` | КСО 5-го поколения |
| `capability_profiles` | 1 | 1920×1080 landscape | ⚠️ Нет `code` колонки (отклонение от ERD) |
| `physical_devices` | 1 | offline | ⚠️ Нет `external_code`, `device_properties` |
| `logical_carriers` | 2 | | ⚠️ Нет `name` колонки |
| `display_surfaces` | 2 | | |
| `manifest_versions` | 19 | | |
| `generated_manifests` | 1 | | |

### Таблицы, которых НЕТ

| Таблица | Нужна для | План создания |
|---|---|---|
| `placements` | Замена kso_placements | Миграция (создать до вставки) |
| `placement_targets` | Targets для placements | Миграция |
| `proof_events` | Замена kso_proof_of_play_events | Миграция |
| `external_code` в physical_devices | device_code из kso_devices | ALTER TABLE ADD COLUMN |
| `device_properties` в physical_devices | KSO-specific поля | ALTER TABLE ADD COLUMN |

---

## 2. Pre-Migration: Schema Changes Required

### 2.1. ALTER physical_devices

```sql
-- Добавить колонки (миграция Alembic)
ALTER TABLE physical_devices ADD COLUMN external_code VARCHAR(64);
ALTER TABLE physical_devices ADD COLUMN device_properties JSONB DEFAULT '{}';

-- Уникальный индекс
CREATE UNIQUE INDEX idx_physical_devices_external_code ON physical_devices(external_code);
```

### 2.2. CREATE placements + placement_targets

```sql
CREATE TABLE placements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    placement_code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    priority INTEGER DEFAULT 0,
    start_date DATE,
    end_date DATE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_placements_campaign ON placements(campaign_id);
CREATE INDEX idx_placements_code ON placements(placement_code);

CREATE TABLE placement_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    placement_id UUID NOT NULL REFERENCES placements(id),
    target_type VARCHAR(20) NOT NULL,
    store_id UUID REFERENCES stores(id),
    display_surface_id UUID REFERENCES display_surfaces(id),
    logical_carrier_id UUID REFERENCES logical_carriers(id),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_placement_targets_placement ON placement_targets(placement_id);
```

### 2.3. CREATE proof_events

```sql
CREATE TABLE proof_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code VARCHAR(128) UNIQUE NOT NULL,
    proof_type VARCHAR(30) NOT NULL DEFAULT 'real_playback',
    device_id UUID REFERENCES physical_devices(id),
    store_id UUID REFERENCES stores(id),
    surface_id UUID REFERENCES display_surfaces(id),
    campaign_id UUID REFERENCES campaigns(id),
    placement_id UUID REFERENCES placements(id),
    creative_id UUID REFERENCES creatives(id),
    rendition_id UUID REFERENCES creative_renditions(id),
    manifest_id UUID REFERENCES manifest_versions(id),
    started_at TIMESTAMPTZ,
    duration_ms INTEGER,
    media_sha256 VARCHAR(64),
    playback_result VARCHAR(20) DEFAULT 'success',
    failure_reason VARCHAR(100),
    device_signature VARCHAR(512),
    channel_type VARCHAR(20) DEFAULT 'KSO',
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_proof_events_device ON proof_events(device_id, received_at);
CREATE INDEX idx_proof_events_campaign ON proof_events(campaign_id, received_at);
CREATE UNIQUE INDEX idx_proof_events_code ON proof_events(event_code);
```

---

## 3. Dry-Run Mapping

### 3.1. kso_devices → physical_devices

**Source (1 row):**
```
id:              b4e7811f-8bd5-45b9-92e5-0a5734cc120a
device_code:     test-dev-seed
store_id:        50eb0a7e-b12d-4346-b054-641ae952c5e2
display_name:    Synthetic KSO Device
status:          active
screen_width:    768
screen_height:   1024
ad_zone_width:   768
ad_zone_height:  1024
channel:         kso
```

**Target:**
```sql
-- DRY-RUN preview (NOT executed):
SELECT 
    'WOULD INSERT INTO physical_devices' as action,
    kd.device_code AS external_code,
    kd.store_id,
    dt.id AS device_type_id,
    CASE kd.status WHEN 'active' THEN 'online' ELSE 'offline' END AS status,
    jsonb_build_object(
        'display_name', kd.display_name,
        'screen_width', kd.screen_width,
        'screen_height', kd.screen_height,
        'ad_zone_width', kd.ad_zone_width,
        'ad_zone_height', kd.ad_zone_height,
        'runtime_version', kd.runtime_version,
        'player_version', kd.player_version,
        'sidecar_version', kd.sidecar_version,
        'legacy_source', 'kso_devices',
        'legacy_id', kd.id::text
    ) AS device_properties,
    kd.created_at,
    kd.updated_at
FROM kso_devices kd
JOIN device_types dt ON dt.code = 'kso_gen5'
WHERE kd.device_code = 'test-dev-seed';
```

**Expected:** 1 row migrated  
**Blocked:** 0  
**Validation:** `SELECT COUNT(*) FROM physical_devices WHERE external_code = 'test-dev-seed'` → 1

### 3.2. kso_placements → placements + placement_targets

**Source (1 row):**
```
id:              19b2da95-7377-498f-a8fb-c79f30291360
placement_code:  test-place-seed
campaign_code:   test-camp-seed
device_code:     test-dev-seed
status:          active
starts_at/ends_at
```

**Target:**
```sql
-- DRY-RUN preview:
SELECT 
    'WOULD INSERT INTO placements' as action,
    kp.placement_code,
    c.id AS campaign_id,
    'Migrated: ' || kp.placement_code AS name,
    kp.status,
    0 AS priority,
    kp.starts_at::date AS start_date,
    kp.ends_at::date AS end_date,
    kp.created_by,
    kp.created_at,
    kp.updated_at
FROM kso_placements kp
JOIN campaigns c ON c.campaign_code = kp.campaign_code;

-- Placement targets:
SELECT
    'WOULD INSERT INTO placement_targets' as action,
    'store' AS target_type,
    s.id AS store_id
FROM kso_placements kp
JOIN physical_devices pd ON pd.external_code = kp.device_code
JOIN stores s ON s.id = pd.store_id;
```

**Expected:** 1 placement + 1 placement_target  
**Blocked:** 0  
**Risk:** placement_code может дублироваться с будущими placements — проверить UNIQUE constraint.

### 3.3. kso_proof_of_play_events → proof_events

**Source (2 rows):**
```
event_code:    d4-direct-fix-v2, d4-synth-20260625191359-0de5dc
device_code:   test-dev-seed
placement_code: test-place-seed
campaign_code: test-camp-seed
creative_code: test-creative-seed
manifest_code: test-manifest-seed
event_type:    test_playback_completed
status:        accepted
duration_ms:   1000
```

**Target:**
```sql
-- DRY-RUN preview:
SELECT 
    'WOULD INSERT INTO proof_events' as action,
    kp.event_code,
    'real_playback' AS proof_type,
    pd.id AS device_id,
    pd.store_id,
    c.id AS campaign_id,
    pl.id AS placement_id,
    cr.id AS creative_id,
    mv.id AS manifest_id,
    kp.played_at AS started_at,
    kp.duration_ms,
    kp.media_ref AS media_sha256,
    CASE kp.event_type WHEN 'test_playback_completed' THEN 'success' ELSE kp.event_type END AS playback_result,
    kp.status,
    'KSO' AS channel_type,
    kp.received_at,
    kp.created_at
FROM kso_proof_of_play_events kp
LEFT JOIN physical_devices pd ON pd.external_code = kp.device_code
LEFT JOIN campaigns c ON c.campaign_code = kp.campaign_code
LEFT JOIN placements pl ON pl.placement_code = kp.placement_code
LEFT JOIN creatives cr ON cr.creative_code = kp.creative_code
LEFT JOIN manifest_versions mv ON mv.manifest_code = kp.manifest_code;
```

**Expected:** 2 rows  
**Blocked:** 0 (если все FK разрешаются)  
**Orphan risk:** manifest_code='test-manifest-seed' — нужно проверить, что manifest_versions содержит такой код.

### 3.4. Orphan Check (dry-run)

```sql
-- Проверить orphan device_code в PoP
SELECT kp.event_code, kp.device_code
FROM kso_proof_of_play_events kp
LEFT JOIN kso_devices kd ON kd.device_code = kp.device_code
WHERE kd.id IS NULL;

-- Проверить orphan campaign_code
SELECT kp.event_code, kp.campaign_code
FROM kso_proof_of_play_events kp
LEFT JOIN campaigns c ON c.campaign_code = kp.campaign_code
WHERE c.id IS NULL;

-- Проверить, что manifest_code существует
SELECT kp.event_code, kp.manifest_code
FROM kso_proof_of_play_events kp
LEFT JOIN manifest_versions mv ON mv.manifest_code = kp.manifest_code
WHERE mv.id IS NULL;
```

---

## 4. Backup Plan

### 4.1. Full DB Backup
```bash
# Команда (не выполнять в A.3):
pg_dump -h localhost -U retail_media -d retail_media_platform \
    -Fc -f /tmp/retail_media_pre_kso_migration_$(date +%Y%m%d_%H%M%S).dump
```

### 4.2. CSV Exports (table-level)
```sql
-- Экспорт критичных таблиц перед миграцией:
COPY kso_devices TO '/tmp/backup_kso_devices.csv' CSV HEADER;
COPY kso_placements TO '/tmp/backup_kso_placements.csv' CSV HEADER;
COPY kso_proof_of_play_events TO '/tmp/backup_kso_pop_events.csv' CSV HEADER;
COPY physical_devices TO '/tmp/backup_physical_devices.csv' CSV HEADER;
```

### 4.3. Backup Validation
```bash
pg_restore --list /tmp/retail_media_pre_kso_migration_*.dump | head -5
```

### 4.4. Хранение
- Backup в `/tmp/` (временное, не в repo)
- Не коммитить backup-файлы
- Исключить через `.git/info/exclude`: `*.dump`, `backup_*.csv`

---

## 5. Validation Plan (после миграции)

```sql
-- 1. Count match
SELECT 'kso_devices' as src, COUNT(*) FROM kso_devices
UNION ALL
SELECT 'physical_devices KSO', COUNT(*) FROM physical_devices WHERE external_code IS NOT NULL;

-- 2. No duplicate external_code
SELECT external_code, COUNT(*) FROM physical_devices 
WHERE external_code IS NOT NULL GROUP BY external_code HAVING COUNT(*) > 1;

-- 3. Every KSO device has device_type
SELECT COUNT(*) FROM physical_devices pd
LEFT JOIN device_types dt ON pd.device_type_id = dt.id
WHERE pd.external_code IS NOT NULL AND dt.id IS NULL;

-- 4. Every KSO device has store
SELECT COUNT(*) FROM physical_devices 
WHERE external_code IS NOT NULL AND store_id IS NULL;

-- 5. Placement count match
SELECT 'kso_placements' as src, COUNT(*) FROM kso_placements
UNION ALL
SELECT 'placements migrated', COUNT(*) FROM placements WHERE placement_code LIKE 'test-place%';

-- 6. PoP event count match
SELECT 'kso_pop' as src, COUNT(*) FROM kso_proof_of_play_events
UNION ALL
SELECT 'proof_events KSO', COUNT(*) FROM proof_events WHERE channel_type = 'KSO';

-- 7. No orphan proof_events
SELECT COUNT(*) FROM proof_events pe
LEFT JOIN physical_devices pd ON pe.device_id = pd.id
WHERE pd.id IS NULL;

-- 8. RLS/scope preserved (advertiser_scope)
-- Ручная проверка: portal показывает те же кампании что и до миграции
```

---

## 6. Rollback Plan

### Stage 1: Immediate Rollback (< 5 минут)
```bash
pg_restore -h localhost -U retail_media -d retail_media_platform \
    --clean --if-exists /tmp/retail_media_pre_kso_migration_*.dump
```

### Stage 2: Partial Rollback (feature flag)
```
USE_UNIVERSAL_DEVICE_MODEL = false
→ Portal/API используют старый read path (kso_devices)
→ Новые данные в physical_devices не затрагиваются
```

### Stage 3: Cleanup (после подтверждения)
```sql
-- Только после полной валидации и approval:
DELETE FROM placement_targets WHERE placement_id IN (SELECT id FROM placements WHERE placement_code LIKE 'test-place%');
DELETE FROM placements WHERE placement_code LIKE 'test-place%';
DELETE FROM proof_events WHERE channel_type = 'KSO';
DELETE FROM physical_devices WHERE external_code = 'test-dev-seed';
-- НЕ удалять kso_* таблицы до отдельного approval!
```

---

## 7. Feature Flag Plan

```python
# config или env variable
USE_UNIVERSAL_DEVICE_MODEL = False  # default

# Этапы включения:
# 1. False — старый read path (kso_devices)
# 2. Shadow — писать в обе модели, читать из старой
# 3. True (test) — читать из physical_devices на dev-стенде
# 4. True (global) — все читают из physical_devices
# 5. Cleanup — удалить kso_* таблицы (отдельный approval)
```

---

## 8. Migration Sequence (A.3 execution plan)

```
1. [ ] ALTER physical_devices: ADD external_code, device_properties
2. [ ] CREATE TABLE placements, placement_targets, proof_events
3. [ ] pg_dump backup
4. [ ] CSV export kso_* tables
5. [ ] DRY-RUN SELECT (подтверждение counts)
6. [ ] INSERT kso_devices → physical_devices (1 row)
7. [ ] INSERT kso_placements → placements (1 row)
8. [ ] INSERT placement_targets (1 row)
9. [ ] INSERT kso_proof_of_play_events → proof_events (2 rows)
10. [ ] Validation queries (counts, orphans, duplicates)
11. [ ] Backend regression (777 tests)
12. [ ] Portal regression (863 tests)
13. [ ] Feature flag: USE_UNIVERSAL_DEVICE_MODEL=true (test only)
14. [ ] Smoke test: portal device listing, campaign view
15. [ ] Approval for cleanup
```

---

## 9. Risks

| Риск | Вероятность | Смягчение |
|---|---|---|
| external_code дубликат | Low (1 строка) | UNIQUE constraint + dry-run check |
| FK resolution fail для PoP | Low | LEFT JOIN в dry-run покажет NULL |
| manifest_code не найден | Medium | Проверить до миграции |
| Регрессия backend/portal | Low | 777+863 тестов ДО и ПОСЛЕ |
| Потеря KSO-specific полей | Low | device_properties JSONB сохраняет всё |
| Seed каналов несоответствие | Medium | Seed определяет 5, в БД 1 — задокументировано |
