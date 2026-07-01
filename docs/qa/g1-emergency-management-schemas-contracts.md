# G.1 — Emergency Management Schemas / Contracts

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

G.1 создаёт Emergency Management domain: schemas, service contracts, validation. Все функции — read-only / dry-run. Реальный останов рекламы запрещён.

---

## Emergency Domain

```
backend/app/domains/emergency/
├── __init__.py      — public API exports
├── schemas.py       — 8 Pydantic v2 моделей
└── service.py       — 7 функций-контрактов
```

---

## Action Types

| Type | Описание |
|---|---|
| `stop_campaign` | Остановить показы кампании |
| `stop_placement` | Остановить показы размещения |
| `stop_channel` | Остановить показы на канале |
| `stop_store` | Остановить показы в магазине |
| `stop_device` | Остановить показы на устройстве |
| `emergency_message` | Экстренное сообщение |
| `resume` | Возобновить после остановки |

---

## Statuses

`draft` → `pending_approval` → `approved` → `active` → `expired` / `cancelled` / `completed` / `rejected`

---

## Target Dimensions

| Dimension | Ключи |
|---|---|
| channel | `channel_id`, `channel_code` |
| store | `store_id`, `store_code` |
| device | `physical_device_id`, `gateway_device_id`, `device_code` |
| campaign | `campaign_id`, `campaign_code` |
| placement | `placement_id`, `placement_code` |
| display_surface | `display_surface_id` |

Минимум одно измерение обязательно. Broad scope (channel/store без device/campaign) — warning.

---

## Dry-run

`dry_run=True` по умолчанию. `dry_run=False` запрещён на G.1 — вызывает `ValueError`. Все функции возвращают `dry_run=True`.

---

## Service Contracts

| Функция | Возвращает | Dry-run? | DB write? |
|---|---|---|---|
| `validate_emergency_action(request)` | `list[EmergencyIssue]` | ✅ | ❌ |
| `preview_emergency_action(db, request)` | `EmergencyActionPreview` | ✅ | ❌ |
| `simulate_emergency_stop(db, request)` | `EmergencyActionResult` | ✅ | ❌ |
| `simulate_emergency_message(db, request)` | `EmergencyActionResult` | ✅ | ❌ |
| `resolve_emergency_targets(target)` | `dict` | ✅ | ❌ |
| `build_emergency_issue(...)` | `EmergencyIssue` | ✅ | ❌ |

---

## Validation Rules

- `action_type` обязателен
- `reason` обязателен (min 1 символ)
- `priority` обязателен
- `target` не должен быть пустым
- `emergency_message` требует `message` content
- `stop_*` не требуют `message`
- `starts_at <= ends_at`
- `duration_seconds > 0`
- `dry_run=false` → `ValueError`
- Broad scope → `broad_emergency_scope` warning
- Critical priority + `requires_approval=False` → warning

---

## Что G.1 НЕ делает

- ❌ Реальный останов рекламы
- ❌ API / endpoints
- ❌ Миграции / таблицы БД
- ❌ Portal
- ❌ Изменение Campaign/Placement/Publication
- ❌ Device Gateway changes
- ❌ KSO Adapter changes
- ❌ Universal Manifest writes
- ❌ GeneratedManifest writes
- ❌ ClickHouse
- ❌ Production switch

---

## Future Permission Model (G.3+)

| Permission | Назначение |
|---|---|
| `emergency.read` | View emergency dashboard |
| `emergency.execute` | Stop/resume/message |
| `emergency.approve` | Approve emergency actions |

В G.1 permissions не создаются.

---

## Future Audit Events (G.3+)

- `emergency.action.previewed`
- `emergency.action.requested`
- `emergency.action.approved`
- `emergency.action.activated`
- `emergency.action.cancelled`
- `emergency.action.expired`
- `emergency.message.previewed`

В G.1 audit не пишется.

---

## Migration Decision

G.1 не создаёт миграции. Если потребуется таблица `emergency_actions` — отдельный gate после contracts approval.

## API Decision

G.1 не создаёт API. API — в G.3.

## Portal Decision

G.1 не меняет portal. Portal — в G.4.

---

## Тесты

| Группа | Тестов |
|---|---|
| Schemas — targets | 6 |
| Schemas — message/create | 7 |
| Schemas — results | 4 |
| Validation | 10 |
| Service contracts | 7 |
| Target resolution | 6 |
| Read-only boundaries | 8 |
| Compatibility | 4 |
| **Total** | **52** |

Backend collection: **2197 / 0 errors**

---

## GO / NO-GO

**✅ GO для G.2 — Emergency Management Service Implementation**

Условия: read-only, без API, без миграций, без portal, без real stop.
