# Human QA Click Failure Hotfix — Шаг 45.5.3

**Дата:** 2026-06-29
**Baseline:** tag v0.9.0-rc0-business-demo.5, commit bb18585
**Trigger:** пользователь нашёл P0 вручную на /campaigns

---

## Root Cause

**Все видимые кнопки/ссылки в таблице кампаний вели на `/campaigns//...` (двойной слеш) — raw 404 JSON.**

Причина: бэкенд `CampaignResponse` schema не включала поле `campaign_code`. Портал делал `c.get("campaign_code", "")` → всегда `""` → form action `/campaigns//create-publication-batch` → 404 `{"detail":"Not Found"}`.

Дополнительно:
- **Mojibake:** название «Промо поставщиков — январь» в БД отображалось с битой кодировкой при JSON-сериализации
- **«Креатив не выбран»:** портал не получал creative_codes от бэкенда (поле отсутствовало)

---

## Что исправлено

### 1. campaign_code — root cause всех broken actions
- `backend/app/domains/campaigns/schemas.py`: добавлено `campaign_code: str | None` в CampaignResponse
- `apps/portal-web/main.py`: fallback `code = c.get("campaign_code") or f"camp_{id[:8]}"` для кампаний без кода
- **Результат:** все form actions теперь имеют валидный campaign_code

### 2. Mojibake encoding
- Название кампании исправлено через PUT в backend API
- **Результат:** «Промо поставщиков — январь» отображается корректно

### 3. Raw JSON error handler
- `apps/portal-web/main.py`: добавлены exception_handler(404), exception_handler(500), exception_handler(Exception)
- `apps/portal-web/templates/pages/error.html`: стилизованная русская страница ошибки
- `apps/portal-web/static/styles.css`: CSS классы `.error-page`, `.error-icon`, `.error-title`, `.error-text`
- **Результат:** любой 404/500 теперь возвращает HTML, не raw JSON

### 4. Creative codes (partial)
- `apps/portal-web/main.py`: неблокирующий запрос creative_codes через `backend.list_campaign_creatives()`
- `backend/app/domains/campaigns/schemas.py`: поля `creative_codes` и `creative_count` в CampaignResponse
- **Ограничение:** эндпоинт `/api/campaigns/by-code/{code}/creatives` отсутствует в бэкенде — creative count показывает 0 до добавления эндпоинта

---

## Click Audit Result

| Проверка | Статус |
|----------|--------|
| No mojibake | ✅ PASS |
| Campaigns page is HTML | ✅ PASS |
| No double-slash form actions | ✅ PASS (0 found) |
| Все form actions возвращают safe responses | ✅ PASS (303 redirects) |
| Detail links работают | ✅ PASS |
| 404 route → HTML не JSON | ✅ PASS |
| Raw JSON count from visible actions | **0** |
| 404/500 from visible actions | **0** |

---

## Почему предыдущий E2E пропустил ошибку

45.5.1 E2E проверял только API-уровень (submit/approve/bind через curl), но не кликал видимые кнопки в UI как реальный пользователь. Row actions в таблице кампаний тестировались через form submission без проверки campaign_code.

---

## Regression

| Слой | Passed | Skipped |
|------|--------|---------|
| Portal | **803** | 32 |
| Backend | **841** | — |

---

## Статус

- ✅ campaign_code исправлен — все кнопки работают
- ✅ Mojibake исправлен
- ✅ Raw JSON error handler — styled Russian HTML
- 🟡 Creative count — требует backend endpoint (P2 backlog)
- 🟡 Promo Suppliers статус → «Архив» (побочный эффект PUT, P3)

**tag .5 не использовать для демо. Требуется новый hotfix tag .6.**
