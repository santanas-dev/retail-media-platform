# G.3 — Emergency API Read-Only / Security Design Gate

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

G.3 добавляет 4 read-only/dry-run API endpoints для Emergency Management. Все требуют `emergency.read`. Execute/activate/approve/cancel endpoints не созданы.

---

## Endpoints

| Метод | Path | Описание | Permission |
|---|---|---|---|
| `GET` | `/api/emergency/capabilities` | action_types, statuses, priorities | `emergency.read` |
| `POST` | `/api/emergency/preview` | Preview emergency action | `emergency.read` |
| `POST` | `/api/emergency/simulate-stop` | Simulate stop/resume | `emergency.read` |
| `POST` | `/api/emergency/simulate-message` | Simulate emergency message | `emergency.read` |

### Явно НЕ созданы

- ❌ `POST /api/emergency/execute`
- ❌ `POST /api/emergency/activate`
- ❌ `POST /api/emergency/approve`
- ❌ `POST /api/emergency/cancel`

---

## Permission

Создана `emergency.read`. Существующая `emergency.manage` (system_admin only) не тронута.

**Новые permissions:**
- `emergency.read` — preview/simulate emergency actions without execution

**НЕ созданы:**
- `emergency.execute`
- `emergency.approve`
- `emergency.manage` (уже существует, не менялась)

### Role assignments

| Роль | `emergency.read` | `emergency.manage` |
|---|---|---|
| system_admin | ✅ | ✅ |
| security_admin | ✅ | ❌ |
| operations | ✅ | ❌ |
| ad_manager | ❌ | ❌ |
| approver | ❌ | ❌ |
| analyst | ❌ | ❌ |
| advertiser | ❌ | ❌ |
| device_service | ❌ | ❌ |

---

## Audit

4 события (fire-and-forget через `audit_business_action`):

| Event | Endpoint |
|---|---|
| `emergency.capabilities.viewed` | GET /capabilities |
| `emergency.action.previewed` | POST /preview |
| `emergency.stop.simulated` | POST /simulate-stop |
| `emergency.message.simulated` | POST /simulate-message |

Все audit:
- Только на успешные requests
- Без secrets/raw payload
- `target_ref = "dry-run"`

---

## Dry-run only

- `dry_run=True` всегда
- `dry_run=False` → 422 (Pydantic `ValueError`)
- `dry_run_only: true` в `/capabilities`
- `real_execution_disabled` warning в каждом ответе

---

## No-secrets

- `validate_no_secrets_in_emergency_payload()` перед каждым ответом
- 23 forbidden ключа
- Рекурсивная проверка keys + values

---

## Read-only

- ❌ Нет execute/activate/approve/cancel
- ❌ Нет `db.add/insert/update/delete`
- ❌ Нет Campaign/Placement writes
- ❌ Нет GeneratedManifest
- ❌ Нет Device Gateway calls
- ❌ Нет KSO Adapter
- ❌ Нет publication flow
- ❌ Нет миграций
- ❌ Нет portal
- ❌ Нет ClickHouse

---

## Тесты

| Слой | Результат |
|---|---|
| G.3 targeted | **63/63** |
| G.2 targeted | **57/57** |
| G.1 targeted | **52/52** |
| Emergency suite | **172/172** |
| Backend collection | **2317 / 0 errors** |

---

## GO / NO-GO

**✅ GO для G.4 — Emergency Portal Read-Only / Dry-Run Control Page**

NO-GO для real emergency execution.  
NO-GO для approval/activation без separate gate.
