# G.4 — Emergency Portal Read-Only / Dry-Run Control Page

**Date:** 2026-07-02  
**Phase:** G (Emergency & Operations)  
**Status:** ✅ COMPLETED  
**Prerequisite:** G.3 Emergency API Read-Only / Security Design Gate  

---

## 1. Summary

Добавлена read-only/dry-run страница «Аварийное управление» в портал. Страница подключается к Emergency API (G.3) и предоставляет:

- Просмотр capabilities (типы действий, приоритеты, dry_run_only)
- Форма preview — предварительная оценка аварийного действия
- Форма simulate stop/resume — симуляция остановки
- Форма simulate emergency message — симуляция экстренного сообщения
- Панель результатов с affected entities, warnings, errors

**Всё — dry-run only. Реальное выполнение отключено.**

---

## 2. Portal Page / Route

| Маршрут | Метод | Страница |
|---|---|---|
| `/emergency` | GET | Страница + capabilities |
| `/emergency` | POST | Обработка форм (preview/simulate-stop/simulate-message) |

### Navigation

- Ссылка «🚨 Аварийное управление» в разделе «Администрирование»
- Видна всем аутентифицированным пользователям (RBAC-проверка на уровне route handler)
- Без `emergency.read` — 403

---

## 3. BackendClient Methods (4)

| Метод | Endpoint |
|---|---|
| `get_emergency_capabilities(access_token)` | `GET /api/emergency/capabilities` |
| `preview_emergency_action(access_token, payload)` | `POST /api/emergency/preview` |
| `simulate_emergency_stop(access_token, payload)` | `POST /api/emergency/simulate-stop` |
| `simulate_emergency_message(access_token, payload)` | `POST /api/emergency/simulate-message` |

---

## 4. UI Blocks

### A. Capabilities
- action_types (stop_campaign, ..., resume, emergency_message)
- priorities (low, normal, high, critical)
- dry_run_only=true

### B. Preview block
- Выбор action_type, priority, reason, target (channel_code, store_code, device_code, campaign_code, placement_code, display_surface_id)
- Кнопка: **«Проверить»**

### C. Simulate stop/resume
- Типы: stop_campaign, stop_placement, stop_channel, stop_store, stop_device, resume
- Кнопка: **«Симулировать остановку»**

### D. Simulate emergency message
- Заголовок, текст, длительность, серьёзность, цель
- Кнопка: **«Симулировать сообщение»**

### E. Result panel
- ok, dry_run, action_type
- affected_channels, affected_stores, affected_devices, affected_campaigns, affected_placements
- warnings, errors
- validation_errors (от 422)

---

## 5. Dry-Run Only Enforcement

- `dry_run` **всегда True** — не отображается как поле формы
- Баннер: «Это dry-run. Реклама не будет остановлена. Реальное выполнение отключено.»
- `dry_run=False` отвергается бэкендом (422)
- Кнопки имеют предупредительные названия: «Проверить», «Симулировать остановку», «Симулировать сообщение»

---

## 6. Forbidden Buttons

❌ НЕ добавлены:
- «Выполнить»
- «Остановить»
- «Активировать»
- «Подтвердить»
- «Применить»

---

## 7. Error Handling

| Код | Портал |
|---|---|
| 403 | «Нет доступа к аварийному управлению» |
| 422 | validation_errors в блоке ошибок |
| 502/504 | «Сервис аварийного управления временно недоступен» |
| Exception | «Сервис аварийного управления временно недоступен» |

---

## 8. No-Secrets

- `_sanitize_emergency_result()` удаляет ключи: password, token, secret, api_key, access_key, private_key, authorization, bearer, cookie, session, jwt, credential, credentials, traceback, stack
- Шаблон не содержит raw credentials/tokens/session/cookie/authorization
- Нет traceback/internal exception в HTML

---

## 9. Read-Only Confirmed

- Нет прямого доступа к БД из портала (BackendClient only)
- Нет execute/activate/approve/cancel
- Нет миграций
- Нет изменений DB schema
- Campaign/Placement/publication/Gateway/KSO/GeneratedManifest не тронуты
- Нет JS/CDN/localStorage

---

## 10. Test Results

| Слой | Результат |
|---|---|
| **G.4 targeted** | **57/57** ✅ |
| Portal regression | 991 passed / 32 skipped / 8 pre-existing errors |
| Emergency suite (G.1–G.3) | 172/172 ✅ |
| Backend collection | 2317 / 0 errors ✅ |
| Backend full run | 2270 passed / 47 pre-existing failures |

Portal regression: 1031 collected (974 baseline + 57 G.4). Рост ожидаемый.

---

## 11. Files

| Файл | Действие |
|---|---|
| `apps/portal-web/backend_client.py` | 🔄 +4 метода |
| `apps/portal-web/rbac.py` | 🔄 +1 mapping |
| `apps/portal-web/templates/base.html` | 🔄 +nav link |
| `apps/portal-web/templates/pages/emergency.html` | 🆕 |
| `apps/portal-web/main.py` | 🔄 +GET/POST routes + helpers |
| `apps/portal-web/tests/test_emergency_portal_g4.py` | 🆕 57 tests |

---

## 12. GO / NO-GO

### ✅ GO для G.5 — Emergency Security Gate

- Портал read-only/dry-run ✅
- Без real execution ✅
- Без execute/activate/approve/cancel ✅
- No-secrets ✅
- Без API/migration/DB/contract изменений ✅

### ❌ NO-GO для:
- Real emergency execution (отдельный design gate)
- Approval/activation (отдельный design gate)
- Staged rollout (G.3 — deferred)
