# PORTAL.1.4 — Manifest / KSO Preview Page: QA Gate

**Date:** 2026-07-02
**Phase:** PORTAL.1.4
**Status:** ✅ COMPLETE

---

## Что добавлено

### Manifests list page (`/packages`)
- Список GeneratedManifest записей с фильтрами (device_code, campaign_code, status)
- KSO check форма для проверки доступности манифеста на устройстве
- Ссылки на детальную страницу каждого манифеста

### Manifest detail page (`/packages/{code}`)
- **Summary:** manifest_code, device_code, campaign_code, placement_code, status, item_count, media_ref_format, даты
- **Body summary:** количество элементов, список creative_code
- **KSO check block:** статус served/no_manifest с описанием legacy endpoint
- **Links:** публикации, кампании, устройства

### Publication integration
- Publication detail: ссылка «Смотреть манифесты» при `generated_manifest_created=true`

### BackendClient
- `get_kso_manifest_status(access_token, device_code)` — проверяет наличие опубликованного манифеста через list_manifests API

---

## Routes

| Метод | Маршрут | Назначение |
|-------|---------|-----------|
| GET | `/packages` | Список манифестов + KSO check форма |
| GET | `/packages/{code}` | Детали манифеста + body summary + KSO статус |
| POST | `/packages/check-kso` | Проверка KSO для device_code |

---

## KSO Endpoint Check

Legacy endpoint `GET /api/device-gateway/kso/{device_code}/manifest` **требует device JWT** — портал не может вызывать его напрямую.

Вместо этого `get_kso_manifest_status()` использует `GET /api/manifests` для поиска опубликованного манифеста по device_code.

**Состояния:**
- **served** — найден published манифест → banner success с деталями
- **no_manifest** — нет published манифеста → banner warning с описанием legacy endpoint

---

## RBAC

`/packages` → `publications.read` (тот же permission, что и публикации)

---

## Security

- ✅ No secrets в шаблонах
- ✅ No traceback
- ✅ No Authorization/Cookie/token/password/api_key
- ✅ No localStorage
- ✅ No CDN
- ✅ No inline JS
- ✅ BackendClient не пишет манифесты
- ✅ KSO/Gateway не меняется

---

## Boundaries

- ✅ No backend API changes
- ✅ No migrations / DB / Docker / .env
- ✅ No GeneratedManifest write
- ✅ No KSO/Gateway changes
- ✅ No production switch

---

## Tests

**PORTAL.1.4 targeted:** 56/56 ✅
- Route/RBAC: 8 | BackendClient: 6 | List rendering: 6 | Detail+KSO: 8
- KSO check: 5 | Publication integration: 3 | Security: 7 | Boundaries: 8 | Regression: 5

**PORTAL.1.1/1.2/1.3:** all pass ✅
**Portal regression:** 1198 passed / 32 skipped / 0 new failures ✅

---

## GO/NO-GO

**✅ GO для PORTAL.1.5 — Campaign Status / Error Improvements**
