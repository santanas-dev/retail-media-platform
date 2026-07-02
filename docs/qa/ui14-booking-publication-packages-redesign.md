# UI.1.4 — Booking + Publication + Packages Pages Redesign

**Date:** 2026-07-02
**Parent:** UI.1.3 (92359d9)
**Status:** ✅ Complete

---

## Изменённые страницы (6)

| Страница | Файл | Тип изменения |
|----------|------|---------------|
| Bookings list | `bookings.html` | Полный редизайн: page-header, section-card для формы создания и таблицы, status-badge, empty-state с действием |
| Booking detail | `booking_detail.html` | Полный редизайн: page-header с title+subtitle+status, metric cards, section-card для info/items/actions, crosslinks-bar |
| Publications list | `publications.html` | Минимальный: page-header wrapper + subtitle обновлён |
| Publication detail | `publication_detail.html` | Полный редизайн: page-header с title+subtitle+status, crosslinks-bar, русская терминология |
| Packages list | `manifests.html` | Полный редизайн: «Пакеты показа» вместо «Манифесты», page-header, section-card для KSO check, status-badge, crosslinks-bar |
| Package detail | `manifest_detail.html` | Полный редизайн: «Пакет показа» вместо «Манифест», page-header, metric cards, section-card для содержимого/КСО, crosslinks-bar |

## Что улучшено на каждой странице

### Bookings list
- page-header с title «Бронирования», subtitle «Резервирование рекламного времени под кампании» и action-кнопкой
- Форма создания в section-card (вместо `<details>`)
- Таблица в section-card с бейджем количества
- status-badge: warning (Черновик), info (Зарезервировано), success (Подтверждено), muted (Отменено)
- empty-state с ссылкой на Планирование

### Booking detail
- page-header с title «Бронирование», кодом, subtitle (кампания + период)
- Status badge в page-header-right
- metric-grid (4 карточки): Статус, Кампания, Период, Элементов
- section-card для информации, элементов бронирования, действий
- action-bar с кнопками Зарезервировать/Подтвердить/Отменить
- crosslinks-bar: Кампании, Планирование, Публикации

### Publications list
- page-header с title «Публикации», обновлённый subtitle (сохранено «Пакеты публикации» для совместимости)

### Publication detail
- page-header с title «Публикация», batch_ref, subtitle (кампания)
- status-badge в page-header-right
- Русская терминология: «техническим переключателем» вместо «feature flag», «пакет показа» вместо «манифест»
- crosslinks-bar: Кампании, Пакеты показа, Аналитика

### Packages list
- page-header с title «Пакеты показа», subtitle, action на Публикации
- KSO check в section-card
- status-badge: success (Опубликован), info (Сформирован)
- empty-state с действием «К публикациям»
- crosslinks-bar: Кампании, Устройства, Публикации, Аналитика, PoP
- «GeneratedManifest» не используется как основной термин

### Package detail
- page-header с title «Пакет показа», кодом, subtitle (устройство + кампания)
- metric-grid (4 карточки): Устройство, Кампания, Элементов, Формат
- «Содержимое пакета» вместо «Содержимое манифеста»
- crosslinks-bar: Публикации, Кампании, Устройства, PoP
- «GeneratedManifest» не используется

## Design system components использованы

`page-header` · `page-title` · `page-subtitle` · `page-back` · `page-actions` · `section-card` · `section-card-header` · `section-card-icon` · `section-card-title` · `section-card-badge` · `section-card-body` · `metric-grid` · `metric-card` · `status-badge` · `banner-*` · `empty-state` · `filter-bar` · `action-bar` · `crosslinks-bar` · `data-table` · `btn-sm` · `btn-primary` · `btn-success` · `btn-danger` · `btn-secondary` · `hint-text`

## Что не менялось

- Backend API
- Backend код
- Portal routes (6 routes — все на месте)
- Permissions / RBAC
- Feature flags
- Бизнес-логика (reserve/confirm/cancel/publish)
- Миграции / DB schema
- Docker / .env
- KSO / Gateway
- Production switch

## Security / No-secrets

- 0 Authorization/Cookie/token/password/secret во всех 6 шаблонах
- 0 `<script>`, 0 CDN, 0 localStorage
- 0 `|safe` фильтр
- 0 Traceback
- Backend-значения экранированы (Jinja2 autoescape)
- «GeneratedManifest» не используется как бизнес-термин

## Test results

| Suite | Tests | Result |
|-------|-------|--------|
| UI.1.4 targeted | 81 | ✅ 81 passed |
| Full portal regression | 1523 | ✅ 1523 passed / 0 failed / 34 skipped |
| Backend integration | 8 errors | ⚠️ Backend not running (expected) |

## Boundaries confirmed

- ✅ No backend code changes
- ✅ No backend API changes
- ✅ No migrations
- ✅ No DB schema changes
- ✅ No Docker/.env changes
- ✅ No route removals
- ✅ No production switch
- ✅ No KSO/Gateway changes

## GO/NO-GO

**✅ GO для UI.1.5 — Analytics + Devices + PoP Pages Redesign**
