# RC0 Visual Polish — 45.1

**Дата:** 2026-06-28
**HEAD (до):** 6fac6a3 (runtime fix)
**Статус:** ✅ Visual gaps closed

---

## Обнаружено аудитом 45.0

Визуальный аудит 18 production-страниц выявил **40+ CSS-классов**, используемых в шаблонах, но отсутствующих в `styles.css`. Из-за этого часть страниц рендерилась браузерными default-стилями:

- `creative_detail.html` — почти полностью без стилей (12 классов)
- `campaigns_create.html` — форма без стилей (20+ классов)
- `admin.html` — баннеры/бейджи/формы без стилей (15+ классов)
- `inventory.html` — KPI-карточки и fill-бары без стилей (10+ классов)
- `deployment.html` — полностью без стилей (3 класса)
- `proof-of-play.html`, `stores.html` — бейджи/легенды без стилей

## Что сделано в 45.1

### CSS (+228 строк в `styles.css`)

Добавлены все недостающие классы с использованием существующих CSS-переменных (тёмная тема):

| Группа | Классы | Страницы |
|--------|--------|----------|
| KPI-карточки | `kpi-grid`, `kpi-card`, `kpi-label`, `kpi-value`, `kpi-card-warning` | creatives, inventory |
| Детали креатива | `card-header`, `card-icon`, `card-badge`, `card-body`, `detail-preview`, `preview-image`, `preview-placeholder`, `detail-grid`, `detail-row`, `detail-label`, `detail-value`, `detail-actions`, `detail-comment` | creative_detail |
| Форма кампании | `form-section`, `form-title`, `form-fieldset`, `form-row`, `create-form`, `business-form`, `days-group`, `days-checkboxes`, `day-label`, `time-window-group`, `custom-time-group`, `time-row`, `time-sep` | campaigns_create |
| Сводка создания | `summary-section`, `summary-grid`, `summary-item`, `summary-label` | campaigns_create |
| Баннеры (legacy) | `error-banner`, `success-banner`, `error-banner-icon/text`, `success-banner-icon/text` | admin |
| Requirements | `requirements-box`, `requirements-title`, `requirements-grid`, `requirements-item`, `requirements-label`, `requirements-value`, `requirements-disabled`, `requirements-forbidden` | admin, login |
| Fill-бары | `fill-bar`, `fill-bar-inner`, `row-detail`, `content-card-header`, `content-card-title` | inventory |
| Бейджи | `badge`, `badge-draft`, `badge-archived`, `badge-online`, `badge-ready`, `badge-active`, `badge-offline`, `badge-unknown`, `badge-hold`, `badge-warning`, `badge-error`, `badge-blocked` | stores, PoP, admin |
| Фильтры/легенды | `filter-toolbar`, `filter-select`, `legend`, `legend-title`, `legend-item`, `action-link` | PoP, stores |
| Развёртывание | `component-list`, `component-item`, `component-status` | deployment |
| Разное | `empty-text`, `export-action`, `w-150`, `alert`, `alert-warning`, `alert-icon` | multiple |

### Исправления шаблонов

| Файл | Исправление |
|------|-------------|
| `campaigns_create.html` | `btn-primary` → `btn btn-primary`, `btn-secondary` → `btn btn-secondary` (4 места) |
| `campaigns_create.html` | Inline-стили светлой темы → CSS-переменные (3 локации) |
| `login.html` | `btn-primary` → `btn btn-primary` |
| `admin.html` | `btn-primary` → `btn btn-primary`, `btn-danger` → `btn btn-danger` |
| `publications.html` | Удалён пустой `<span class="note-text"></span>` |
| `reports.html` | Удалён пустой `<span class="note-text"></span>` |

### Guard-тесты (4 новых)

| Тест | Проверка |
|------|----------|
| `test_visual_pages_render_200` | 9 страниц с visual gaps → 200/302/303 |
| `test_no_light_theme_inline_styles` | 12 запрещённых светлых цветов → отсутствуют на всех страницах |
| `test_no_empty_note_text` | Пустые `<span class="note-text">` → отсутствуют |
| (undefined CSS guard в backlog) | Сложный тест с whitelist — deferred до 45.1.1 |

### `_FakeBackendClient` расширен

Добавлены методы для inventory-страниц: `get_inventory_snapshot`, `get_inventory_availability`, `get_inventory_forecast`.

---

## Что НЕ менялось

- ❌ Бизнес-логика — 0 изменений
- ❌ RBAC/RLS/audit trail — не тронуты
- ❌ Maker-checker — не тронут
- ❌ Lifecycle публикаций — не тронут
- ❌ Отчётная логика — не тронута
- ❌ Физическая КСО/SSH/X11/Chromium/runner/sidecar/PoP — не запускались
- ❌ Scanner E2E/long-run/sidecar sync — не выполнялись
- ❌ Production AV — не включён
- ❌ Существующие теги — не переписаны

---

## Связанные документы

- `docs/product/rc0-demo-launch-note-45-0-2.md`
- `docs/product/rc0-release-notes-44-6.md`
- `docs/product/business-demo-route-44-6.md`
- `docs/audit/deviation-register-44-0.md`
- `CHANGELOG.md`
