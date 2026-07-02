# PORTAL.1.5 — Campaign Status / Error Improvements: QA Gate

**Date:** 2026-07-02
**Phase:** PORTAL.1.5
**Status:** ✅ COMPLETE

---

## Что улучшено

### Campaign detail page
- **Workflow checklist** — 9 шагов (кампания → креатив → размещение → согласование → бронирование → публикация → опубликовано → пакет показа → КСО)
- **Progress bar** — текстовая индикация прогресса (N/9, X%)
- **Next action** — автоматическое определение следующего действия на основе кросс-доменных данных
- **Cross-links** — ссылки на планирование, бронирования, публикации, пакеты показа, отчёты (с учётом RBAC)

### Campaign list page
- Добавлен «Пакеты показа» в цепочку шагов

### BackendClient
- Использует существующие методы: `list_bookings`, `list_publication_batches`, `list_manifests`

---

## Как работает workflow checklist

Функция `_build_campaign_workflow()` собирает данные из нескольких доменов:

1. **Кампания создана** — всегда done (если статус не пустой)
2. **Креатив добавлен и одобрен** — проверяет bound_creatives
3. **Размещение создано** — проверяет schedules + placements
4. **Кампания одобрена** — статус in_review/approved
5. **Бронирование создано** — через `list_bookings()`, фильтр по campaign_id
6. **Пакет публикации создан** — через `list_publication_batches()`, фильтр по campaign code в comment
7. **Публикация выполнена** — статус batch = published
8. **Пакет показа создан** — через `list_manifests()`, фильтр по campaign_code
9. **Доступен для КСО** — manifest status = published

---

## Cross-links (RBAC-aware)

| Ссылка | Permission |
|--------|-----------|
| 📊 Планирование | `planning.read` |
| 📅 Бронирования | `bookings.read` |
| 📋 Публикации | `publications.read` |
| 📜 Пакеты показа | `publications.read` |
| 📈 Отчёты | `reports.read` |

---

## Security

- ✅ No secrets в шаблонах
- ✅ No traceback
- ✅ No Authorization/Cookie/token/password/api_key
- ✅ No localStorage / CDN / JS
- ✅ Cross-links скрыты без прав

---

## Boundaries

- ✅ No backend API changes
- ✅ No migrations / DB / Docker / .env
- ✅ No production switch
- ✅ No KSO/Gateway changes

---

## Tests

**PORTAL.1.5 targeted:** 47/47 ✅
- Workflow: 9 | Cross-links: 7 | Detail rendering: 6 | List: 5
- Security: 7 | Boundaries: 8 | Regression: 5

**PORTAL.1.1-1.4:** all pass ✅
**Portal regression:** 1245 passed / 32 skipped / 0 new failures ✅

---

## GO/NO-GO

**✅ GO для PORTAL.1.6 — Analytics / Error States / Cross-Linking**
