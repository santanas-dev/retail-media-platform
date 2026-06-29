# KSO Data Migration Rollback Plan — A.3

> **Дата:** 2026-06-29 | **Этап:** A.3 EXECUTED → A.3.2 VERIFIED  
> **Статус:** РАБОЧИЙ — backup проверен (2.2 MB, 634 entries), rollback доступен

---

## 1. Rollback Triggers

Автоматический rollback при:
- ❌ Orphan FK в любых таблицах после миграции
- ❌ Backend regression FAIL
- ❌ Portal regression FAIL
- ❌ Row counts не совпадают (dry-run vs actual)
- ❌ RBAC/RLS нарушен (scope checks fail)

Ручной rollback при:
- ⚠️ Portal UI показывает неверные данные
- ⚠️ Device listing пустой или дублированный
- ⚠️ Campaign/placement связи нарушены

---

## 2. Rollback Procedure

### Stage 1: Full DB Restore (< 5 минут)

```bash
# Остановить backend/portal если нужно
# Восстановить из backup:
pg_restore -h localhost -U retail_media -d retail_media_platform \
    --clean --if-exists /tmp/retail_media_pre_kso_migration_*.dump

# Перезапустить сервисы
# Проверить: curl http://127.0.0.1:8421/health
```

### Stage 2: Partial Rollback (Feature Flag)

```
USE_UNIVERSAL_DEVICE_MODEL = false
```

При false:
- Portal читает устройства через старый kso_devices path
- Новые записи в physical_devices не затрагиваются
- Можно отлаживать без полного restore

### Stage 3: Selective Delete (если только часть миграции проблемна)

```sql
-- Удалить только мигрированные записи, сохранив pre-existing:
DELETE FROM placement_targets 
WHERE placement_id IN (
    SELECT id FROM placements 
    WHERE placement_code IN ('test-place-seed')
);

DELETE FROM placements 
WHERE placement_code IN ('test-place-seed');

DELETE FROM proof_events 
WHERE channel_type = 'KSO';

DELETE FROM physical_devices 
WHERE external_code IN (SELECT device_code FROM kso_devices);

-- НЕ удалять:
-- - kso_devices (source of truth)
-- - kso_placements
-- - kso_proof_of_play_events
-- - pre-existing physical_devices rows
```

---

## 3. Rollback Validation

После rollback проверить:
- [ ] `SELECT COUNT(*) FROM kso_devices` = исходное значение
- [ ] `SELECT COUNT(*) FROM physical_devices` = исходное значение (до миграции)
- [ ] Backend regression: 777/0
- [ ] Portal regression: 863/0
- [ ] Portal device listing работает
- [ ] Campaign view корректен

---

## 4. Cleanup After Successful Migration

**ТОЛЬКО после полной валидации и approval:**

```sql
-- Шаг выполняется в отдельном A.3.x approval step
-- НЕ выполнять в A.3!

-- После подтверждения что physical_devices работает:
-- DROP TABLE kso_proof_of_play_events;  -- мигрированы в proof_events
-- DROP TABLE kso_placements;            -- мигрированы в placements
-- DROP TABLE kso_devices;               -- мигрированы в physical_devices
```

---

## 5. Backup Retention

| Артефакт | Срок хранения | Место |
|---|---|---|
| pg_dump .dump файл | 30 дней после успешной миграции | `/tmp/` |
| CSV exports kso_* | 30 дней | `/tmp/` |
| Dry-run SQL output | Постоянно (в docs) | `docs/architecture/` |

---

## 6. Decision Matrix

| Ситуация | Действие |
|---|---|
| Миграция успешна, все тесты pass | ✅ Продолжить, feature flag = true |
| 1-2 теста fail, не критично | ⚠️ Feature flag = false, fix, retry |
| Row counts mismatch | ❌ Rollback Stage 1 (full restore) |
| FK orphans | ❌ Rollback Stage 1 |
| Regression FAIL | ❌ Rollback Stage 1 |
| Portal broken | ❌ Rollback Stage 1 |
