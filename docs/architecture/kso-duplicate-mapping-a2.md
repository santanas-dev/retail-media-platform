# KSO Duplicate Mapping — A.2 → A.3 Migration Plan

> **Дата:** 2026-06-29 | **Этап:** A.2 (проектирование)  
> **Исполнение:** A.3 (dry-run + миграция данных)  
> **Статус:** ПРОЕКТ (миграция не выполняется)

---

## 1. Mapping Summary

| Source Table | Target Table | Тип миграции | Риск |
|---|---|---|---|
| `kso_devices` | `physical_devices` | 1:1 | Medium |
| `kso_placements` | `placements` + `placement_targets` | 1:2 (split) | Medium |
| `kso_proof_of_play_events` | `proof_events` | 1:1 + нормализация | Low |
| `campaign_targets` | `placement_targets` | трансформация | Medium |

---

## 2. kso_devices → physical_devices

### 2.1. Field Mapping

| kso_devices | physical_devices | Transform | Nullable |
|---|---|---|---|
| id | id | Прямое копирование | — |
| device_code | external_code | Прямое копирование | NOT NULL |
| store_id | store_id | Прямое копирование | NOT NULL |
| — | device_type_id | FK→device_types WHERE code='KSO_LINUX' | NOT NULL |
| display_name | device_properties→'display_name' | JSONB | ✅ |
| status | status | map: 'active'→'online', 'inactive'→'offline' | NOT NULL |
| — | device_properties→'ukms_version' | Из kso_devices.ukms_version | ✅ |
| — | device_properties→'hidden_on_touch' | Из kso_devices.hidden_on_touch | ✅ |
| created_at | created_at | Прямое | |
| updated_at | updated_at | Прямое | |
| — | hardware_fingerprint | NULL (не было в kso_devices) | ✅ |
| — | serial_number | NULL (не было) | ✅ |
| — | zone_label | NULL | ✅ |
| — | installed_at | kso_devices.created_at | ✅ |
| — | last_heartbeat_at | NULL | ✅ |

### 2.2. Pre-migration validation
```sql
-- Проверить, что device_code уникален в kso_devices
SELECT device_code, COUNT(*) FROM kso_devices GROUP BY device_code HAVING COUNT(*) > 1;

-- Проверить, что store_id валиден
SELECT d.device_code FROM kso_devices d 
LEFT JOIN stores s ON d.store_id = s.id WHERE s.id IS NULL;
```

### 2.3. Rollback
```sql
DELETE FROM physical_devices WHERE external_code IN (SELECT device_code FROM kso_devices);
```
Данные в `kso_devices` НЕ удаляются до подтверждения миграции.

### 2.4. Feature flag
`USE_UNIVERSAL_DEVICE_MODEL` — переключает device gateway и portal на `physical_devices`.

---

## 3. kso_placements → placements + placement_targets

### 3.1. Field Mapping

**kso_placements → placements:**

| kso_placements | placements | Transform |
|---|---|---|
| id | id | Копирование |
| placement_code | placement_code | Копирование |
| campaign_id | campaign_id | Копирование (через campaign_code) |
| name | name | Копирование |
| status | status | Копирование |
| priority | priority | Копирование |
| created_at/updated_at | created_at/updated_at | Копирование |
| — | start_date/end_date | Из campaign.planned_start/end_date |
| — | created_by | Из campaign.created_by |

**kso_placements + campaign_targets → placement_targets:**

| Source | placement_targets |
|---|---|
| kso_placements.store_id | store_id |
| campaign_targets.branch_id | branch_id |
| campaign_targets.cluster_id | cluster_id |
| campaign_targets.display_surface_id | display_surface_id |
| campaign_targets.logical_carrier_id | logical_carrier_id |
| 'store' | target_type (если store_id) |
| 'branch' | target_type (если branch_id) |

### 3.2. Rollback
placement_targets удаляются по placement_id IN (SELECT id FROM kso_placements).

---

## 4. kso_proof_of_play_events → proof_events

### 4.1. Field Mapping

| kso_proof_of_play_events | proof_events | Transform |
|---|---|---|
| event_code | event_code | Прямое |
| device_code | device_id | JOIN physical_devices ON external_code |
| placement_code | placement_id | JOIN placements ON placement_code |
| campaign_code | campaign_id | JOIN campaigns ON campaign_code |
| creative_code | creative_id | JOIN creatives ON creative_code |
| manifest_code | manifest_id | JOIN manifest_versions ON manifest_code |
| played_at | started_at | Копирование |
| duration_ms | duration_ms | Копирование |
| media_ref | media_sha256 | Копирование |
| event_type | proof_type | map: 'impression'→'real_playback' |
| received_at | received_at | Копирование |
| — | store_id | JOIN physical_devices.store_id |
| — | playback_result | DEFAULT 'success' |
| — | channel_type | 'KSO' |

### 4.2. Risk: FK resolution
Если device_code/placement_code/etc не находятся в новых таблицах — строка пропускается с логом. Это низкий риск для test data.

### 4.3. Rollback
```sql
DELETE FROM proof_events WHERE event_code IN (SELECT event_code FROM kso_proof_of_play_events);
```

---

## 5. campaign_targets → placement_targets

Выполняется ПОСЛЕ создания placements. Каждый campaign_target привязывается к placement той же campaign.

### 5.1. Mapping
```sql
INSERT INTO placement_targets (placement_id, target_type, branch_id, cluster_id, store_id, display_surface_id, logical_carrier_id, created_at)
SELECT p.id, ct.target_type, ct.branch_id, ct.cluster_id, ct.store_id, ct.display_surface_id, ct.logical_carrier_id, ct.created_at
FROM campaign_targets ct
JOIN placements p ON p.campaign_id = ct.campaign_id;
```

---

## 6. kso_manifest_projection.py → Universal Manifest Projection

| Текущий модуль | Новый модуль | Что меняется |
|---|---|---|
| `KsoSafeManifestItem` | `SafeManifestItem` | Убрать префикс KSO |
| `kso_manifest_projection.py` | `manifest_projection.py` | Универсальный manifest |
| KSO-specific поля | `adapter_payload` JSONB | Канальные параметры в payload |
| `device_code` FK | `physical_devices.external_code` FK | Универсальная модель |

---

## 7. Порядок миграции (A.3)

1. **Создать колонки** (external_code, device_properties в physical_devices) — миграция БД
2. **Создать таблицы** (placements, placement_targets, proof_events) — миграция БД
3. **KSO devices** → physical_devices (dry-run → backup → миграция)
4. **KSO placements** → placements + placement_targets
5. **Campaign targets** → placement_targets
6. **Валидация**: проверка FK, counts match
7. **Feature flag**: включить USE_UNIVERSAL_DEVICE_MODEL для тестового контура
8. **KSO PoP** → proof_events (можно отложить до ClickHouse)
9. **Удаление deprecated таблиц** (после подтверждения)

---

## 8. Риски

| Риск | Вероятность | Смягчение |
|---|---|---|
| device_code конфликтует с существующими physical_devices | Low | Проверить UNIQUE constraint до миграции |
| Placement без campaign | Low | FK constraint + валидация |
| Потеря KSO-specific полей | Low | device_properties JSONB сохраняет все |
| FK resolution для PoP | Medium | Skip + log для ненайденных ссылок |
