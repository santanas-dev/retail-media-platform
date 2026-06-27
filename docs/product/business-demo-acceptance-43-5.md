# Business Demo Acceptance — 43.5

**Date:** 2026-06-16  
**Baseline:** HEAD (43.5)  
**Status:** ✅ Ready for business demo (backend-only)

---

## Цель демонстрации

Показать бизнес-пользователю полный цикл рекламной кампании в Retail Media Platform:
**креатив → кампания → расписание → согласование → публикация → плановая отчётность.**

Весь сценарий выполняется через портал без физической КСО, сканера, Chromium и sidecar.
Физическая доставка и фактические показы — следующий этап после закрытия approval gates.

---

## Что показываем

| Этап | Страница | Что демонстрируем |
|---|---|---|
| 1. Креатив | `/creatives` | Загрузка PNG/JPEG/MP4, предпросмотр, проверка 768×1024 |
| 2. Кампания | `/campaigns` | Создание, редактирование, привязка креативов, статусы |
| 3. Расписание | `/schedule` | Создание schedule, слоты по дням, временные окна, занятость |
| 4. Согласование | `/approvals` | Request approval, maker-checker, approve/reject с комментарием |
| 5. Публикация | `/publications` | Batch lifecycle, manifest generation, backend publish |
| 6. Отчётность | `/reports` | Кампании по статусам, занятость эфира, конфликты, CSV export |
| KPI-сводка | `/dashboard` | Platform summary, pipeline, pilot readiness, план действий |
| Приёмка | `/readiness` | Acceptance checklist, «Что готово», быстрые ссылки |

---

## Что не показываем

| Исключено | Причина |
|---|---|
| Физическая доставка manifest на КСО | Approval gate не пройден |
| Proof of Play (фактические показы) | Нет physical PoP flow |
| Scanner E2E | Сканер отсутствует |
| Sidecar sync на КСО | Не approved |
| 48h+ long-run | Не выполнялся |
| Fleet rollout | Не утверждён |
| UKM5 БД / чеки / оплаты / фискальные данные | Вне scope портала |

---

## Пошаговый сценарий демонстрации

### Шаг 1: Креатив (`/creatives`)
1. Нажать «+ Загрузить креатив»
2. Выбрать файл (PNG/JPEG, рекомендовано 768×1024)
3. Указать код, название, категорию
4. Нажать «Загрузить»
5. Показать карточку креатива с превью и статусом

### Шаг 2: Кампания (`/campaigns/create`)
1. Нажать «+ Создать кампанию»
2. Заполнить: campaign_code, название, даты
3. Нажать «Создать»
4. На странице `/campaigns` привязать креатив (форма «+Креатив»)
5. Показать статус кампании и список креативов

### Шаг 3: Расписание (`/schedule`)
1. Заполнить форму создания расписания: код, название, даты, часовой пояс
2. Добавить слоты (день недели, время начала/конца)
3. Показать таблицу слотов
4. Проверить занятость эфира (форма с device_code и диапазоном дат)

### Шаг 4: Согласование (`/approvals`)
1. На странице кампании нажать «→ Запросить согласование»
2. На `/approvals` показать карточку заявки с campaign detail
3. Подчеркнуть maker-checker: «нельзя согласовать собственный запрос»
4. Принять решение: «✓ Одобрить» или «✗ Отклонить» с комментарием

### Шаг 5: Публикация (`/publications`)
1. На странице кампании нажать «📦 Подготовить публикацию»
2. На `/publications` показать batch lifecycle pipeline (draft → ... → published)
3. Нажать «→ На согласование», затем «📋 Generate manifest»
4. Показать статус «Manifest готов»
5. Нажать «🚀 Publish (backend)» — подчеркнуть: backend-only, не physical KSO
6. Показать красный NO-GO баннер про physical delivery

### Шаг 6: Отчётность (`/reports`)
1. Показать distribution bars «Кампании по статусам»
2. Проверить занятость эфира (прогресс-бар с порогами)
3. Показать конфликты расписания
4. Нажать «📥 campaigns_export.csv», «📥 publications.csv»
5. Подчеркнуть: «Фактические показы появятся после physical PoP flow»

### Шаг 7: Dashboard (`/dashboard`)
1. Platform Summary — stat-grid с distribution bars
2. Advertising Pipeline — 6 шагов с ссылками и счётчиками
3. Pilot Readiness — 5 P0 blockers, статус 🔴 NO-GO
4. Business Next Actions — 6 карточек с ссылками

### Шаг 8: Readiness (`/readiness`)
1. Device KPI — ready/warning/blocked/unknown
2. «Что уже готово» — checklist из 8 backend/portal возможностей
3. «Сценарий демонстрации» — pipeline с ссылками
4. «Что заблокировано» — 5 P0 blockers
5. «Следующий шаг после сканера» — последовательность действий
6. Acceptance checklist — 13 пунктов для самостоятельной приёмки

---

## Критерии успешной приёмки

| # | Критерий | Проверка |
|---|---|---|
| AC-01 | Креатив загружен и approved | `/creatives` — видна карточка, превью работает |
| AC-02 | Кампания создана, креатив привязан | `/campaigns` — creative_code в списке |
| AC-03 | Расписание создано, слоты настроены | `/schedule` — хотя бы 1 слот |
| AC-04 | Согласование запрошено и принято | `/approvals` — решение видно |
| AC-05 | Publication batch создан | `/publications` — batch_ref в списке |
| AC-06 | Manifest сгенерирован в backend | `/publications` — статус «Manifest готов» |
| AC-07 | Backend публикация выполнена | `/publications` — статус «Опубликовано» |
| AC-08 | CSV export доступен | `/reports` — campaigns.csv, publications.csv |
| AC-09 | Dashboard отражает реальные KPI | `/dashboard` — числа не нулевые после заполнения |
| AC-10 | Readiness page показывает честный статус | `/readiness` — 🔴 NO-GO, 5 blockers, acceptance checklist |
| AC-11 | Нет видимых test-kso/dev/internal labels | Grep production UI — 0 matches |
| AC-12 | Нет JS/CDN/localStorage | Grep templates — 0 matches |
| AC-13 | Нет raw UUID/backend URL/secrets в HTML | Регрессия safety tests |

---

## Known Limitations

| Ограничение | Статус |
|---|---|
| Физическая доставка manifest на КСО | ❌ Заблокировано (B-03) |
| Sidecar sync на КСО | ❌ Заблокировано (B-04) |
| Фактические показы (PoP) | ❌ Нет данных до physical gate |
| Scanner E2E | ❌ Сканер отсутствует |
| 48h+ long-run | ❌ Не выполнялся |
| Fleet rollout | ❌ Не утверждён |
| Manifest delivery validation | ❌ B-03 |
| Sidecar sync validation | ❌ B-04 |
| Offline/degraded mode | ❌ Не реализован (G-03) |
| XLSX export | ❌ CSV only (D-RP-01) |

---

## Physical Blockers (unchanged)

| Blocker | Status |
|---|---|
| B-01: HW Scanner E2E | ❌ Not executed |
| B-02: 48h+ Long-run | ❌ Not executed |
| B-03: Manifest Delivery to Physical KSO | ❌ Not approved |
| B-04: Sidecar Sync Physical Start | ❌ Not executed |
| B-06: Fleet Rollout Approval | ❌ Not approved |

---

## Next Steps After Scanner Appears

1. Подключить физический сканер → Scanner E2E (PHASE_SCANNER_E2E_APPROVED)
2. Manifest delivery → физическая КСО (PHASE_PHYSICAL_DELIVERY_APPROVED)
3. Sidecar sync → physical start (PHASE_SIDECAR_SYNC_APPROVED)
4. 48h+ long-run → мониторинг (PHASE_LONG_RUN_APPROVED)
5. GO/NO-GO решение → пилот одного КСО (PHASE_FLEET_ROLLOUT_APPROVED)
6. Fleet rollout → масштабирование

---

## Related Documents

- `docs/runbooks/one-kso-pilot-runbook.md` — пилотный runbook
- `docs/runbooks/kso-fallback-rollback-runbook.md` — откат и восстановление
- `docs/runbooks/physical-approval-gates.md` — approval tokens
- `docs/audit/pilot-readiness-gap-register.md` — gap register
- `docs/audit/technical-debt-register.md` — технический долг
- `CHANGELOG.md` — история изменений
