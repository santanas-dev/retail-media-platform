# KSO Migration Approval Checklist — A.3.1

> **Дата:** 2026-06-29 | **Этап:** A.3.1  
> **Статус:** ⏳ AWAITING APPROVAL

---

## Decision Required

| Вопрос | Ответ |
|---|---|
| Выполнить реальную миграцию A.3? | ⬜ YES / ⬜ NO |
| Утверждающий | _______________ |
| Дата утверждения | ____.____.2026 |
| Комментарий | |

**Фраза для утверждения:** `APPROVE A.3 EXECUTION`

---

## Что будет сделано при утверждении

| Шаг | Действие | Время |
|---|---|---|
| 1 | pg_dump backup | < 1 мин |
| 2 | Alembic upgrade (ALTER + 3× CREATE) | < 30 сек |
| 3 | 4× INSERT (1+1+1+2 строки) | < 5 сек |
| 4 | 18 validation queries | < 1 мин |
| 5 | Backend regression (777) | ~20 сек |
| 6 | Portal regression (863) | ~8 сек |
| 7 | Feature flag = false (shadow) | мгновенно |
| 8 | Report + commit | < 1 мин |

**Итого: ~5 минут.** Rollback: < 5 минут.

---

## Pre-Flight Checks (перед миграцией)

- [ ] Git status: clean
- [ ] HEAD: `60f3f8d` (A.3 dry-run)
- [ ] Backend regression: 777/0, portal: 863/0
- [ ] Backend + portal запущены
- [ ] Эта строка: `APPROVE A.3 EXECUTION` получена ✅

---

## Schema Changes (после утверждения)

- [ ] `ALTER TABLE physical_devices ADD COLUMN external_code VARCHAR(64)`
- [ ] `ALTER TABLE physical_devices ADD COLUMN device_properties JSONB`
- [ ] `CREATE UNIQUE INDEX idx_physical_devices_external_code`
- [ ] `CREATE TABLE placements (...)`
- [ ] `CREATE TABLE placement_targets (...)`
- [ ] `CREATE TABLE proof_events (...)`

---

## Data Migration (после схемы)

- [ ] `INSERT INTO physical_devices ... FROM kso_devices` → 1 row
- [ ] `INSERT INTO placements ... FROM kso_placements` → 1 row
- [ ] `INSERT INTO placement_targets ...` → 1 row
- [ ] `INSERT INTO proof_events ... FROM kso_proof_of_play_events` → 2 rows

---

## Validation (после данных)

- [ ] Row counts match expected (1+1+1+2)
- [ ] No duplicate external_code
- [ ] No orphan FKs
- [ ] proof_type='real_playback' для всех KSO events
- [ ] channel_type='KSO' для всех мигрированных
- [ ] device_properties содержит 'display_name', 'legacy_source'
- [ ] kso_* таблицы НЕ удалены

---

## Regression (после валидации)

- [ ] Backend: `python3 -m unittest discover -s backend/tests -v` → 777/0
- [ ] Portal: `python3 -m unittest discover -s apps/portal-web/tests -v` → 863/0
- [ ] Pytest compliance: `pytest apps/portal-web/tests/compliance_46_1_test.py` → 19/0

---

## Security Gates (после regression)

- [ ] RLS/scope 47/47
- [ ] Audit coverage 20/20
- [ ] Maker-checker enforced
- [ ] Raw JSON: 0
- [ ] JS/CDN/localStorage: 0
- [ ] Secrets/leaks: 0
- [ ] Visible test/seed/None: 0

---

## Feature Flag (после security)

- [ ] `USE_UNIVERSAL_DEVICE_MODEL=false` (default)
- [ ] Portal: старый read path работает
- [ ] При `=true`: portal показывает physical_devices

---

## Post-Migration Commit

- [ ] `git add` migration files
- [ ] `git commit -m "🗄 Execute KSO data migration to universal model"`
- [ ] `git status` clean

---

## Not In This Step

- [ ] ❌ kso_* таблицы НЕ дропаются
- [ ] ❌ Старый read path код НЕ удаляется
- [ ] ❌ Seed каналы НЕ добавляются
- [ ] ❌ Новые портал-страницы НЕ создаются
- [ ] ❌ Business logic НЕ меняется

---

## Sign-off

| Роль | Имя | Подпись | Дата |
|---|---|---|---|
| Владелец проекта | | | |
| Разработчик (Hermes) | Auto | `60f3f8d` (dry-run) | 2026-06-29 |
