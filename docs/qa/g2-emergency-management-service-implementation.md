# G.2 — Emergency Management Service Implementation

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

G.2 реализует read-only service logic: DB target resolution, enriched preview, stop/message simulation, no-secrets validation. Всё dry-run. Без API/миграций/portal.

---

## Что реализовано

### target resolution (`resolve_emergency_targets(db, target)`)

DB-запросы через существующие модели:
- **Channel** → `Channel` → `PhysicalDevice` (через `DeviceType`)
- **Store** → `Store` → `PhysicalDevice` (по `store_id`)
- **Device** → `PhysicalDevice` (по `id` / `external_code`)
- **Campaign** → `Campaign` → `Placement` (по `campaign_id`)
- **Placement** → `Placement` → `Campaign` (по `campaign_id`)
- **DisplaySurface** → `DisplaySurface` (по `id`)

Все запросы — SELECT. При отсутствии данных — без traceback. Partial resolution → warning.

### preview (`preview_emergency_action(db, request)`)

- Валидация → target resolution → no-secrets check
- Возвращает `EmergencyActionPreview` с affected counts и warnings/errors
- Всегда `dry_run=True`

### simulate stop (`simulate_emergency_stop(db, request)`)

- Поддерживает: STOP_CAMPAIGN, STOP_PLACEMENT, STOP_CHANNEL, STOP_STORE, STOP_DEVICE, RESUME
- Не меняет Campaign/Placement/Publication
- Не создаёт GeneratedManifest
- Не вызывает Device Gateway
- Возвращает `EmergencyActionResult` с summary

### simulate message (`simulate_emergency_message(db, request)`)

- Только EMERGENCY_MESSAGE
- Проверяет message content
- Не создаёт manifest
- Не вызывает Gateway
- Возвращает `EmergencyActionResult`

### no-secrets (`validate_no_secrets_in_emergency_payload(payload)`)

- 23 forbidden ключа: password, token, secret, api_key, bearer, cookie, session, jwt, etc.
- Рекурсивная проверка keys + values
- Вызывается перед возвратом preview/result

---

## Dry-run

- `dry_run=True` всегда
- `dry_run=False` запрещён моделью (`ValueError`)
- Все результаты содержат `real_execution_disabled` info

---

## Что G.2 НЕ делает

- ❌ Реальный останов рекламы
- ❌ API / endpoints
- ❌ Миграции
- ❌ Portal
- ❌ DB writes (только SELECT)
- ❌ Campaign/Placement изменения
- ❌ GeneratedManifest writes
- ❌ Device Gateway calls
- ❌ KSO Adapter changes
- ❌ Publication flow
- ❌ ClickHouse

---

## Уточнение по G.1 counts

G.1: 6 функций (validate, preview, resolve_targets, simulate_stop, simulate_message, build_issue).  
G.2: +1 (validate_no_secrets_in_emergency_payload) = **7 функций**.

---

## Тесты

| Слой | Тестов |
|---|---|
| G.2 targeted | **57** |
| G.1 targeted | **52** |
| Emergency suite (G.1+G.2) | **109/109** |
| Backend collection | **2254 / 0 errors** |

### G.2 test groups

| Группа | Тестов |
|---|---|
| Validation | 8 |
| Target resolution | 10 |
| Preview | 7 |
| Simulate stop | 9 |
| Simulate message | 5 |
| No-secrets | 5 |
| Read-only boundaries | 9 |
| Compatibility | 4 |

---

## GO / NO-GO

**✅ GO для G.3 — Emergency API Read-Only / Security Design Gate**

NO-GO для real execution API.  
NO-GO для production stop без approval workflow.
