# E.1 — KSO Adapter Dry-Run Payload Builder

> **Дата:** 2026-07-01
> **Этап:** E.1 — KSO Adapter Implementation
> **Предыдущий:** E.0 (commit `70c32db`)
> **Результат:** ✅ GO для E.2 KSO Adapter Validation + No-Secrets Tests

---

## Что создано

### KsoAdapter (`backend/app/domains/adapters/kso_adapter.py`)

Класс `KsoAdapter(AdapterContract)` — dry-run адаптер для канала KSO.

| Метод | Описание |
|---|---|
| `adapter_name = "kso"` | Идентификатор адаптера |
| `channel_code = "kso"` | Код канала |
| `supports("kso")` | True только для "kso" |
| `build_payload(context)` | Строит KSO-safe dry-run payload |
| `validate_payload(payload)` | Валидирует структуру payload |
| `simulate_delivery(payload)` | Dry-run симуляция |

Адаптер **авто-регистрируется** при импорте через `_register()`.

---

## Поля payload

### Обязательные

| Поле | Источник |
|---|---|
| `adapter_name` | "kso" (hardcoded) |
| `channel_code` | "kso" (hardcoded) |
| `dry_run` | True (hardcoded) |
| `device_code` | `context.devices[0].device_code` |
| `placement_code` | `context.placement_code` |

### Опциональные

| Поле | Источник |
|---|---|
| `campaign_id` | `context.campaign_id` |
| `store_id` | `context.devices[0].store_id` |
| `resolution_width` / `height` | `surface.resolution` (parse "WxH") |
| `orientation` | `surface.orientation` |
| `proof_type` | `surface.proof_type` |
| `schedule.date_from` / `date_to` | `context.start_date` / `end_date` |
| `items[].creative_code` | `context.creative_codes[i]` |
| `items[].slot_order` | индекс в списке |
| `items[].media_type` | "unknown" (резолвится в E.2+) |

### Warnings (structured)

| Условие | Warning |
|---|---|
| Нет devices | "No devices found in orchestrator context" |
| Нет device_code | "Missing device_code for device" |
| Нет placement_code | "Missing placement_code in orchestrator context" |
| Нет creative_codes | "No creative codes in orchestrator context" |
| Нет schedule | "No schedule in context" |
| Нет resolution | "No resolution information available" |
| Нет proof_type | "No proof_type in capability profile" |

---

## Validation rules

`validate_payload()` проверяет:

1. `adapter_name == "kso"` и `channel_code == "kso"`
2. `dry_run == True`
3. `device_code` обязательно
4. `placement_code` обязательно
5. Нет forbidden secret words в ключах и значениях (рекурсивно)
6. `proof_type` из разрешённого списка
7. `resolution_width` / `resolution_height` > 0
8. `duration_seconds` > 0 для каждого item

Разрешённые proof_type: real_playback, idle_impression, template_applied, label_ack, controller_ack, delivery_ack.

---

## simulate_delivery()

- Вызывает `validate_payload()`
- При ошибках: `ok=False`, ошибки в `errors`
- При успехе: `ok=True`, details с device_code, placement_code, items_count
- Не обращается к сети, не пишет в БД

---

## Adapter Registry

Адаптер зарегистрирован через `app.domains.adapters.registry.register_adapter()`.
`select_adapter("kso")` теперь работает и возвращает `KsoAdapter`.

---

## Что не менялось

- Legacy KSO production flow (`/kso/{device_code}/manifest`)
- GeneratedManifest таблица
- Publication flow (`generate_manifests`, `publish_batch`)
- Device Gateway endpoints
- Planning API / portal

---

## Test Results

| Слой | Результат |
|---|---|
| E.1 targeted | **55/55** ✅ |
| Planning + E.1 suite | **309/309** ✅ |
| Backend collection | **1715** (0 errors) |

---

## GO ✅ для E.2 — KSO Adapter Validation + No-Secrets Tests
