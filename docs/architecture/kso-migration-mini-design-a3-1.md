# KSO Migration Mini-Design & Approval Gate — A.3.1

> **Дата:** 2026-06-29 | **Этап:** A.3.1 (APPROVAL GATE)  
> **Статус:** ⏳ AWAITING APPROVAL  
> **Основание:** A.3 Dry-Run + A.2 Architecture Contracts

---

## 0. Что будет сделано (если approved)

**Миграция 4 строк из 3 KSO-таблиц в универсальную модель v2.5.**

| Source | Target | Строк |
|---|---|---|
| `kso_devices` (1 row) | `physical_devices` | 1 |
| `kso_placements` (1 row) | `placements` | 1 |
| `kso_placements` → targets | `placement_targets` | 1 |
| `kso_proof_of_play_events` (2 rows) | `proof_events` | 2 |

**Плюс schema migration:**
- ALTER `physical_devices`: +2 колонки
- CREATE `placements`, `placement_targets`, `proof_events`

---

## 1. Execution Sequence

```
Step 1: Pre-check       — git clean, regression 777/863, backup
Step 2: pg_dump         — full DB backup
Step 3: Schema          — ALTER + CREATE (Alembic)
Step 4: Data INSERT     — 4 INSERT statements
Step 5: Validation      — 18 checks
Step 6: Regression      — 777 backend + 863 portal
Step 7: Feature flag    — USE_UNIVERSAL_DEVICE_MODEL=false (shadow)
Step 8: Decision        — Rollback OR continue
Step 9: Cleanup         — NOT in A.3 (separate approval)
```

---

## 2. Schema Migration (DETAILED)

### 2A. ALTER physical_devices

```sql
-- Forward (Alembic upgrade):
ALTER TABLE physical_devices 
    ADD COLUMN external_code VARCHAR(64),
    ADD COLUMN device_properties JSONB DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX idx_physical_devices_external_code 
    ON physical_devices(external_code) 
    WHERE external_code IS NOT NULL;

-- Rollback (Alembic downgrade):
DROP INDEX IF EXISTS idx_physical_devices_external_code;
ALTER TABLE physical_devices 
    DROP COLUMN IF EXISTS external_code,
    DROP COLUMN IF EXISTS device_properties;
```

| Поле | Тип | Nullable | Default | FK |
|---|---|---|---|---|
| `external_code` | VARCHAR(64) | YES | NULL | UNIQUE partial index |
| `device_properties` | JSONB | NO | `'{}'` | — |

**Почему nullable:** pre-existing physical_devices (1 row от seed) не имеет external_code.  
**Почему partial index:** позволяет NULL для non-KSO устройств без нарушения UNIQUE.

### 2B. CREATE placements

```sql
CREATE TABLE placements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    placement_code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    priority INTEGER NOT NULL DEFAULT 0,
    start_date DATE,
    end_date DATE,
    created_by UUID REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_placements_campaign ON placements(campaign_id);
CREATE INDEX idx_placements_code ON placements(placement_code);

-- Rollback:
DROP TABLE IF EXISTS placements CASCADE;
```

| FK | Target | ON DELETE |
|---|---|---|
| campaign_id | campaigns.id | RESTRICT |
| created_by | users.id | RESTRICT |

**RLS:** advertiser_scope через campaign.advertiser_id  
**Audit:** placement.created, placement.updated

### 2C. CREATE placement_targets

```sql
CREATE TABLE placement_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    placement_id UUID NOT NULL REFERENCES placements(id) ON DELETE CASCADE,
    target_type VARCHAR(20) NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE RESTRICT,
    display_surface_id UUID REFERENCES display_surfaces(id) ON DELETE SET NULL,
    logical_carrier_id UUID REFERENCES logical_carriers(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_placement_targets_placement ON placement_targets(placement_id);

-- Rollback:
DROP TABLE IF EXISTS placement_targets CASCADE;
```

### 2D. CREATE proof_events

```sql
CREATE TABLE proof_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code VARCHAR(128) UNIQUE NOT NULL,
    proof_type VARCHAR(30) NOT NULL DEFAULT 'real_playback',
    device_id UUID REFERENCES physical_devices(id) ON DELETE RESTRICT,
    store_id UUID REFERENCES stores(id) ON DELETE SET NULL,
    surface_id UUID REFERENCES display_surfaces(id) ON DELETE SET NULL,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE RESTRICT,
    placement_id UUID REFERENCES placements(id) ON DELETE SET NULL,
    creative_id UUID REFERENCES creatives(id) ON DELETE RESTRICT,
    rendition_id UUID REFERENCES creative_renditions(id) ON DELETE SET NULL,
    manifest_id UUID REFERENCES manifest_versions(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ,
    duration_ms INTEGER,
    media_sha256 VARCHAR(64),
    playback_result VARCHAR(20) DEFAULT 'success',
    failure_reason VARCHAR(100),
    device_signature VARCHAR(512),
    channel_type VARCHAR(20) DEFAULT 'KSO',
    proof_metadata JSONB DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_proof_events_device ON proof_events(device_id, received_at);
CREATE INDEX idx_proof_events_campaign ON proof_events(campaign_id, received_at);
CREATE INDEX idx_proof_events_channel ON proof_events(channel_type, received_at);
CREATE UNIQUE INDEX idx_proof_events_code ON proof_events(event_code);

-- Rollback:
DROP TABLE IF EXISTS proof_events CASCADE;
```

---

## 3. Data Migration (DETAILED)

### 3A. kso_devices → physical_devices (1 row)

```sql
INSERT INTO physical_devices (
    id, external_code, store_id, device_type_id, status,
    device_properties, created_at, updated_at
)
SELECT
    kd.id,
    kd.device_code,
    kd.store_id,
    dt.id,
    CASE kd.status WHEN 'active' THEN 'online' ELSE 'offline' END,
    jsonb_build_object(
        'display_name', kd.display_name,
        'screen_width', kd.screen_width,
        'screen_height', kd.screen_height,
        'ad_zone_width', kd.ad_zone_width,
        'ad_zone_height', kd.ad_zone_height,
        'channel', kd.channel,
        'runtime_version', kd.runtime_version,
        'player_version', kd.player_version,
        'sidecar_version', kd.sidecar_version,
        'legacy_source', 'kso_devices',
        'legacy_id', kd.id::text
    ),
    kd.created_at,
    kd.updated_at
FROM kso_devices kd
JOIN device_types dt ON dt.code = 'kso_gen5'
WHERE kd.device_code = 'test-dev-seed'
  -- Idempotency: skip if already migrated
  AND NOT EXISTS (
    SELECT 1 FROM physical_devices 
    WHERE external_code = kd.device_code
  );
```

**Expected:** 1 row inserted  
**Idempotency:** `WHERE NOT EXISTS` предотвращает дубликат

### 3B. kso_placements → placements (1 row)

```sql
INSERT INTO placements (
    id, placement_code, campaign_id, name, status,
    priority, start_date, end_date, created_by, created_at, updated_at
)
SELECT
    kp.id,
    kp.placement_code,
    c.id,
    COALESCE(kp.placement_code, 'Migrated placement'),
    kp.status,
    COALESCE(kp.slot_order, 0),
    kp.starts_at::date,
    kp.ends_at::date,
    kp.created_by,
    kp.created_at,
    kp.updated_at
FROM kso_placements kp
JOIN campaigns c ON c.campaign_code = kp.campaign_code
WHERE NOT EXISTS (
    SELECT 1 FROM placements WHERE placement_code = kp.placement_code
);
```

### 3C. placement_targets (1 row)

```sql
INSERT INTO placement_targets (
    placement_id, target_type, store_id, created_at
)
SELECT
    p.id,
    'store',
    kd.store_id,
    p.created_at
FROM kso_placements kp
JOIN placements p ON p.placement_code = kp.placement_code
JOIN kso_devices kd ON kd.device_code = kp.device_code
WHERE NOT EXISTS (
    SELECT 1 FROM placement_targets 
    WHERE placement_id = p.id AND store_id = kd.store_id
);
```

**Fallback:** если display_surface ещё не создан для этого устройства — target_type='store' с прямым store_id. При создании display_surfaces позже можно добавить более точный таргетинг.

### 3D. kso_proof_of_play_events → proof_events (2 rows)

```sql
INSERT INTO proof_events (
    id, event_code, proof_type, device_id, store_id,
    campaign_id, placement_id, creative_id, manifest_id,
    started_at, duration_ms, media_sha256,
    playback_result, channel_type,
    proof_metadata, received_at, created_at
)
SELECT
    kp.id,
    kp.event_code,
    'real_playback',
    pd.id,
    pd.store_id,
    c.id,
    pl.id,
    cr.id,
    mv.id,
    kp.played_at,
    kp.duration_ms,
    kp.media_ref,
    CASE kp.event_type 
        WHEN 'test_playback_completed' THEN 'success' 
        ELSE kp.event_type 
    END,
    'KSO',
    jsonb_build_object(
        'legacy_event_type', kp.event_type,
        'legacy_status', kp.status,
        'legacy_source', 'kso_proof_of_play_events'
    ),
    kp.received_at,
    kp.created_at
FROM kso_proof_of_play_events kp
LEFT JOIN physical_devices pd ON pd.external_code = kp.device_code
LEFT JOIN campaigns c ON c.campaign_code = kp.campaign_code
LEFT JOIN placements pl ON pl.placement_code = kp.placement_code
LEFT JOIN creatives cr ON cr.creative_code = kp.creative_code
LEFT JOIN manifest_versions mv ON mv.manifest_code = kp.manifest_code
WHERE NOT EXISTS (
    SELECT 1 FROM proof_events WHERE event_code = kp.event_code
);
```

---

## 4. Backup & Rollback

### 4.1. Backup (Step 2)

```bash
# Full DB backup (before any changes)
pg_dump -h localhost -U retail_media -d retail_media_platform \
    -Fc -f /tmp/retail_media_pre_a3_migration_$(date +%Y%m%d_%H%M%S).dump

# Verify
pg_restore --list /tmp/retail_media_pre_a3_migration_*.dump | wc -l

# CSV exports (extra safety)
psql -h localhost -U retail_media -d retail_media_platform << 'SQL'
COPY kso_devices TO '/tmp/backup_kso_devices.csv' CSV HEADER;
COPY kso_placements TO '/tmp/backup_kso_placements.csv' CSV HEADER;
COPY kso_proof_of_play_events TO '/tmp/backup_kso_pop.csv' CSV HEADER;
COPY physical_devices TO '/tmp/backup_physical_devices.csv' CSV HEADER;
SQL
```

### 4.2. Rollback (Step 8)

**Immediate rollback (< 5 min):**
```bash
pg_restore -h localhost -U retail_media -d retail_media_platform \
    --clean --if-exists /tmp/retail_media_pre_a3_migration_*.dump
```

**Feature flag rollback:**
```
USE_UNIVERSAL_DEVICE_MODEL = false
→ Portal/API используют старый kso_devices read path
```

**Selective rollback:**
```sql
-- Удалить только мигрированные строки:
DELETE FROM proof_events WHERE event_code IN (SELECT event_code FROM kso_proof_of_play_events);
DELETE FROM placement_targets WHERE placement_id IN (SELECT id FROM placements WHERE placement_code IN (SELECT placement_code FROM kso_placements));
DELETE FROM placements WHERE placement_code IN (SELECT placement_code FROM kso_placements);
DELETE FROM physical_devices WHERE external_code IN (SELECT device_code FROM kso_devices);
-- НЕ трогать ALTER TABLE — колонки могут остаться
```

**Stop criteria — немедленный rollback если:**
- ❌ Row counts не совпадают
- ❌ Orphan FK обнаружены
- ❌ Backend regression FAIL
- ❌ Portal regression FAIL
- ❌ RBAC/RLS нарушен (scope check fail)

---

## 5. Validation Checklist (Step 5-6)

### Row Counts
- [ ] `SELECT COUNT(*) FROM physical_devices WHERE external_code='test-dev-seed'` = 1
- [ ] `SELECT COUNT(*) FROM placements WHERE placement_code='test-place-seed'` = 1
- [ ] `SELECT COUNT(*) FROM placement_targets` = 1+existing
- [ ] `SELECT COUNT(*) FROM proof_events WHERE channel_type='KSO'` = 2

### Data Integrity
- [ ] No duplicate external_code in physical_devices
- [ ] No orphan placement_targets (FK→placements)
- [ ] No orphan proof_events (FK→physical_devices)
- [ ] All proof_events have proof_type='real_playback'
- [ ] device_properties содержит legacy поля
- [ ] Legacy kso_* таблицы сохранены (не удалены)

### Regression
- [ ] Backend: 777/0
- [ ] Portal: 863/0 (20 skipped OK)
- [ ] Pytest compliance: 19/0

### Security Gates
- [ ] RLS/scope 47/47
- [ ] Audit coverage 20/20
- [ ] Maker-checker enforced
- [ ] Raw JSON: 0
- [ ] JS/CDN/localStorage: 0

### Feature Flag
- [ ] `USE_UNIVERSAL_DEVICE_MODEL=false` (default)
- [ ] Portal показывает устройства корректно (старый read path)
- [ ] При `=true` portal читает из physical_devices (тестовый режим)

---

## 6. Risk Matrix

| # | Риск | P | Impact | Mitigation | Detection | Rollback |
|---|---|---|---|---|---|---|
| R1 | Schema migration fail (ALTER/CREATE) | Low | High | Проверено на dev, простые DDL | Alembic error | pg_restore |
| R2 | Duplicate external_code | Low | Low | `WHERE NOT EXISTS` + UNIQUE index | Validation query #2 | Row delete |
| R3 | Missing campaign FK для placement | Low | Medium | JOIN проверен в dry-run | FK constraint → INSERT fail | Transaction rollback |
| R4 | Missing display_surface для target | Low | Low | Fallback: target_type='store' | Validation query | Row delete |
| R5 | Proof event duplicate | Low | Low | `WHERE NOT EXISTS` + UNIQUE(event_code) | Validation query #1 | Row delete |
| R6 | Feature flag accidentally enabled | Low | Medium | Default=false, env var | Portal показывает двойные устройства | Установить false |
| R7 | Portal breaks (old route expects kso table) | Low | High | Feature flag разделяет read path | Portal regression 863 | Feature flag=false |
| R8 | Rollback pg_restore fails | Low | High | pg_dump verified before migration | pg_restore --list check | CSV + raw SQL restore |
| R9 | Backup corrupted | Very Low | High | Проверить pg_restore --list | Валидация backup до миграции | CSV exports |
| R10 | Regression tests fail after migration | Low | High | Dry-run проверен, только 4 строки | Regression run | pg_restore |

---

## 7. Feature Flag Design

```python
# config или env:
USE_UNIVERSAL_DEVICE_MODEL = os.getenv("USE_UNIVERSAL_DEVICE_MODEL", "false") == "true"

# Default: false — старый read path
# После валидации: true — новый read path (physical_devices)
# Cleanup: удалить старый код + kso_* таблицы (отдельный approval)
```

| Mode | Read Path | Write Path | Portal |
|---|---|---|---|
| `false` (default) | kso_devices | kso_devices | Старый |
| `false` + shadow | kso_devices | physical_devices + kso_devices | Старый |
| `true` (test) | physical_devices | physical_devices | Новый |
| `true` (global) | physical_devices | physical_devices | Новый |

---

## 8. ⚠️ APPROVAL GATE

```
╔══════════════════════════════════════════════════════════════╗
║                    APPROVAL REQUIRED                         ║
║                                                              ║
║  Для выполнения реальной миграции требуется явное             ║
║  подтверждение владельца проекта.                             ║
║                                                              ║
║  Формат подтверждения:                                        ║
║                                                              ║
║    APPROVE A.3 EXECUTION                                      ║
║                                                              ║
║  Без этой строки реальную миграцию НЕ выполнять.              ║
║                                                              ║
║  Миграция затронет:                                           ║
║    - ALTER physical_devices (+2 колонки)                      ║
║    - CREATE placements, placement_targets, proof_events       ║
║    - INSERT 4 строки (1 device + 1 placement + 2 PoP)        ║
║    - Код backend/portal НЕ меняется                           ║
║    - kso_* таблицы НЕ удаляются                               ║
║    - RBAC/RLS/audit НЕ затрагиваются                          ║
║                                                              ║
║  Риск: Low (4 строки, backup, rollback < 5 минут)            ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 9. Post-Approval Checklist

После получения `APPROVE A.3 EXECUTION`:

- [ ] 1. Убедиться: git clean, HEAD актуален
- [ ] 2. Regression: backend 777, portal 863
- [ ] 3. pg_dump backup
- [ ] 4. Alembic: upgrade (ALTER + CREATE)
- [ ] 5. Data INSERT (4 statements, transactional)
- [ ] 6. Validation queries (18 checks)
- [ ] 7. Regression repeat
- [ ] 8. Feature flag: false (default, shadow mode)
- [ ] 9. Commit migration
- [ ] 10. Report: commit hash, counts, gates

---

## 10. Что НЕ делается в A.3

- ❌ Удаление kso_* таблиц (отдельный approval)
- ❌ Удаление старого read path кода (после валидации)
- ❌ Изменение business logic
- ❌ Включение feature flag = true (сначала shadow mode)
- ❌ Создание каналов из seed (android_tv, price_checker, esl, led_shelf_banner)
- ❌ Production deployment
