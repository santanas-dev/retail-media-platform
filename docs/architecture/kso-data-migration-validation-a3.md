# KSO Data Migration Validation — A.3

> **Дата:** 2026-06-29 | **Этап:** A.3 (EXECUTED) → A.3.2 (VERIFIED ✅)  
> **Статус:** ВЫПОЛНЕНО — 17/17 validation checks pass | Safety Gate: A.3.2 ✅

---

## 1. Pre-Migration Gates

- [ ] pg_dump backup создан и проверен
- [ ] CSV exports kso_* таблиц созданы
- [ ] Dry-run SQL выполнен без ошибок
- [ ] 0 орфанов в kso_proof_of_play_events
- [ ] 0 дубликатов device_code / placement_code
- [ ] Backend regression: 777/0
- [ ] Portal regression: 863/0
- [ ] Git status clean

## 2. Post-Migration Validation

### 2.1. Row Counts

| Проверка | Ожидаемый результат |
|---|---|
| physical_devices с external_code IS NOT NULL | = COUNT(kso_devices) = 1 |
| placements с placement_code LIKE 'test-place%' | = COUNT(kso_placements) = 1 |
| placement_targets для migrated placements | = COUNT(kso_placements) = 1 |
| proof_events с channel_type='KSO' | = COUNT(kso_proof_of_play_events) = 2 |

### 2.2. FK Integrity

| Проверка | SQL |
|---|---|
| No orphan physical_devices | `SELECT COUNT(*) FROM physical_devices pd LEFT JOIN stores s ON pd.store_id=s.id WHERE pd.external_code IS NOT NULL AND s.id IS NULL` → 0 |
| No orphan placement_targets | `SELECT COUNT(*) FROM placement_targets pt LEFT JOIN placements p ON pt.placement_id=p.id WHERE p.id IS NULL` → 0 |
| No orphan proof_events | `SELECT COUNT(*) FROM proof_events pe LEFT JOIN physical_devices pd ON pe.device_id=pd.id WHERE pd.id IS NULL` → 0 |

### 2.3. Data Integrity

| Проверка | SQL |
|---|---|
| external_code matches | `SELECT kd.device_code, pd.external_code FROM kso_devices kd JOIN physical_devices pd ON pd.external_code=kd.device_code` — все строки совпадают |
| device_properties содержит legacy поля | `SELECT device_properties->>'display_name' FROM physical_devices WHERE external_code='test-dev-seed'` → 'Synthetic KSO Device' |
| proof_type = real_playback | `SELECT DISTINCT proof_type FROM proof_events WHERE channel_type='KSO'` → только 'real_playback' |

### 2.4. Business Logic

- [ ] Portal показывает КСО устройства (через physical_devices)
- [ ] Campaign детали доступны
- [ ] Publication/manifest статус корректен
- [ ] RBAC/RLS не нарушен (advertiser_scope)
- [ ] Audit trail не затронут

## 3. Regression Gates

```bash
# Backend
cd backend && python3 -m unittest discover -s tests -v
# Expected: 777/0

# Portal  
cd apps/portal-web && python3 -m unittest discover -s tests -v
# Expected: 863/0 (20 skipped OK)
```

## 4. Security Gates

- [ ] RLS/scope 47/47
- [ ] Audit coverage 20/20
- [ ] Maker-checker enforced
- [ ] Raw JSON: 0
- [ ] JS/CDN/localStorage: 0
- [ ] Secrets/leaks: 0

## 5. Smoke Tests

- [ ] `curl http://127.0.0.1:8421/health` → 200
- [ ] `curl http://127.0.0.1:8422/` → 303
- [ ] Portal login работает
- [ ] Device listing показывает KSO устройство
- [ ] Campaign view корректен

## 6. Stop Criteria

Остановить и откатить если:
- ❌ Row counts не совпадают
- ❌ Orphan FK обнаружены
- ❌ Backend regression FAIL
- ❌ Portal regression FAIL
- ❌ RBAC/RLS нарушен
