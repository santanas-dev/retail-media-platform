# PORTAL.1.3 — Publication Workflow Page: QA Gate

**Date:** 2026-07-02
**Phase:** PORTAL.1.3
**Status:** ✅ COMPLETE

---

## Что добавлено

### Detail page + publish result display
- **GET `/publications/{batch_id}`** — детальная страница пакета публикации
- **Publish result block** — отображение полного `PublishBatchResult` из backend

### Улучшения
- **Publish route** — теперь сохраняет `pub_result` в session и редиректит на detail page
- **List page** — добавлены ссылки «Детали» на каждый batch

### BackendClient
- `get_publication` — alias для `get_publication_batch`
- Все остальные методы уже существовали

---

## Routes

| Метод | Маршрут | Назначение | Изменения |
|-------|---------|-----------|-----------|
| GET | `/publications` | Список пакетов | + detail links |
| GET | `/publications/{id}` | Детали пакета | **NEW** |
| POST | `/publications/batch/{id}/publish` | Публикация | Улучшен |

---

## Блоки detail page

### A. Batch summary
- ID, campaign_id, status, comment, created_at, updated_at

### B. Actions
- Request approval (draft)
- Generate manifest (approved)
- Publish (manifest_generated)
- Cancel (all except published/cancelled)

### C. Publish Result Block (PORTAL.1.3)
Показывает `PublishBatchResult` из backend:

**Success:**
- `generated_manifest_created` — ✅/❌
- `generated_manifest_count` — число
- `generated_manifest_details` — таблица (manifest_code, device_code, status)
- `next_step` — с особым отображением для `generated_manifest_write_disabled`

**Feature flag OFF:**
- `real_publication_disabled` → banner «Публикация отключена feature flag»
- `generated_manifest_write_disabled` → warning в next_step + info banner

---

## Обработка feature flags

Портал НЕ читает env-флаги. Backend возвращает:
- **ENABLE_REAL_PUBLICATION=false** → 422 `real_publication_disabled` → banner warning
- **ENABLE_REAL_PUBLICATION=true, ENABLE_GENERATED_MANIFEST_WRITE=false** → success + `generated_manifest_created=false` + next_step warning
- **Both flags true** → success + manifest count + details

---

## Security

- ✅ No secrets в шаблонах
- ✅ No traceback
- ✅ No Authorization/Cookie/token/password/api_key
- ✅ No localStorage
- ✅ No CDN
- ✅ No inline JS
- ✅ `_safe_error()` для backend-ошибок

---

## Boundaries

- ✅ No backend API changes
- ✅ No migrations
- ✅ No DB schema changes
- ✅ No Docker/.env changes
- ✅ No booking/manifest write from portal
- ✅ No production switch
- ✅ No KSO/Gateway changes

---

## Tests

**PORTAL.1.3 targeted:** 53/53 ✅
- Route/RBAC: 8
- BackendClient: 5
- List rendering: 5
- Detail + publish result: 9
- Workflow: 6
- Security: 7
- Boundaries: 9
- Regression: 4

**PORTAL.1.1:** 42/42 ✅
**PORTAL.1.2:** 56/56 ✅
**Portal regression:** 1142 passed / 32 skipped ✅

---

## GO/NO-GO

**✅ GO для PORTAL.1.4 — Manifest / KSO Preview Page**
