# UI.1 — Portal UI / UX Redesign: Design Gate

**Phase:** UI.1.0 (Design Gate)  
**Previous:** PORTAL.1.8 — Functional Completion Closure (`18ed93f`)  
**Status:** ✅ Design Gate — GO for UI.1.1  

---

## 1. Executive Summary

PORTAL.1 закрыл функциональные gaps портала: 7 workflow-страниц, RBAC, cross-linking. Портал функционально готов, но **визуально и UX-не готов** для бизнес-демонстрации.

UI.1 — редизайн портала **без изменения функциональности**: тот же backend, те же routes, та же логика. Меняются только templates + CSS.

**Цель:** портал должен выглядеть как production-grade Enterprise SaaS продукт, пригодный для демонстрации бизнес-пользователям.

---

## 2. Why UI.1 Is Needed

PORTAL.1 закрыл функциональные gaps, но выявил UX/UI debt:

| Проблема | Влияние |
|----------|---------|
| CSS фрагментирован (пустые секции, дубли) | Нестабильный рендеринг, трудно расширять |
| Нет дизайн-системы | Каждая страница выглядит по-своему |
| Навигация без RBAC | device_service видит меню администрирования |
| Статусы не стандартизированы | Разный стиль на разных страницах |
| Формы без единого стиля | Поля разбросаны, нет группировки |
| Таблицы без стандарта | Разная плотность, нет sticky headers |
| Технические UUID видны | Бизнес-пользователь видит `inventory_unit_id` |
| Нет `.banner-success` в CSS | Шаблоны используют класс, которого нет |
| `.btn-sm` определён дважды | CSS конфликты, нестабильный рендеринг |

---

## 3. Current Portal Functional Baseline

| Аспект | Статус |
|--------|--------|
| Backend | 2695 tests, 0 errors |
| Portal routes | 15 RBAC-guarded (PORTAL.1) |
| Portal pages | 27+ (7 новых workflow) |
| PORTAL.1 tests | 359 targeted, 1337 regression |
| Feature flags | All default `False` |
| Production switch | NO-GO |

---

## 4. Current UX/UI Problems

### A. Navigation

| Проблема | Описание |
|----------|----------|
| Nav links unconditional | Все 27 пунктов видны всем пользователям. Guards блокируют на уровне route (403), но меню не фильтруется. |
| Группировка слабая | 3 секции (Основное/Аналитика/Администрирование), но mixing: planning в «Аналитика», publications в «Основное» — нелогично. |
| device_service видит всё | Роль device_service видит admin/emergency ссылки в меню. |
| Нет коллапса | Сайдбар всегда развёрнут, нет иконок-only режима. |

### B. Visual Hierarchy

| Проблема | Описание |
|----------|----------|
| Карточки однородны | `section-card` везде одинаков, нет визуальной иерархии важных блоков. |
| Заголовки inconsistent | `<h2>` на одних страницах, `section-card-header` на других. |
| Статусы не стандартизированы | `status-badge-status-badge-*` на одних, inline mapping на других. |

### C. Design System

| Проблема | Описание |
|----------|----------|
| CSS фрагментирован | 533 строки, но: формы пустые, таблицы пустые, кнопки дублируются, `.btn-sm` определён дважды. |
| Нет компонентной модели | `.section-card` есть, но нет page-header, metric-card, action-bar, filter-panel, workflow-step. |
| Alert-система неполная | `.banner-info` есть, `.banner-success` используется в шаблонах но НЕ определён в CSS. |

### D. Forms

| Проблема | Описание |
|----------|----------|
| Формы технические | Поля без группировки, placeholder'ы типа `store_id`, `inventory_unit_id`. |
| Нет единого стиля | Фильтр-форма на planning — голые `<label><input>`, форма создания кампании — другое. |
| Ошибки не у полей | Backend-ошибки показываются баннером сверху, а не рядом с проблемным полем. |

### E. Tables

| Проблема | Описание |
|----------|----------|
| Нет стандарта | `data-table` на одних страницах, inline table на других. |
| Разная плотность | Где-то `padding: 8px`, где-то `12px`. |
| Статусы в таблицах разные | Где-то pill-бейджи, где-то текст. |
| Технические ID видны | `inventory_unit_code` вместо «Блок КСО-12». |

### F. Status / Workflow

| Проблема | Описание |
|----------|----------|
| Статусы inconsistent | Campaign detail использует `status-badge`, workflow checklist — другой стиль. |
| Progress bar только на workflow | Нет прогресс-индикатора для кампании в целом. |
| Next action не выделен | Баннер `banner-info` — слабый визуальный приоритет. |

### G. Error / Empty States

| Проблема | Описание |
|----------|----------|
| Empty states минимальны | Просто текст `<div class="empty-state">`, без иконки, без action. |
| Error баннеры inconsistent | `alert-error` на planning, `banner-info` на других. |
| Backend unavailable не отличим от других ошибок | Нет визуального различия. |

### H. Responsive

| Проблема | Описание |
|----------|----------|
| Сайдбар фиксированный | 200px всегда, на узких экранах сжимает контент. |
| Нет media queries | Кроме `prefers-reduced-motion`. |
| Таблицы не адаптируются | Горизонтальный скролл только если браузер даёт. |

### I. Business Demo Readiness

| Проблема | Описание |
|----------|----------|
| Технические термины | `inventory_unit_id`, `GeneratedManifest`, `feature flag` — не бизнес-язык. |
| UUID видны | `store_id` вместо «Магазин 473 — Центральный». |
| Нет логотипа/брендинга | «KSO v1» в хедере. |
| Терминология inconsistent | Где-то «Кампания», где-то «Campaign». |

---

## 5. Design Principles

| # | Принцип | Детали |
|---|---------|--------|
| 1 | **SSR only** | Никакого client-side JS. Вся логика на сервере через Jinja2. |
| 2 | **No frontend framework** | Чистый HTML + CSS. Без React/Vue/Svelte. |
| 3 | **No CDN / external deps** | Все ресурсы локальные. Без Google Fonts, CDN CSS. |
| 4 | **No localStorage / cookies in UI** | Только httpOnly session cookie. |
| 5 | **Vanilla CSS** | Без препроцессоров (Sass/Less). Только CSS custom properties. |
| 6 | **No backend changes** | Routes, API, бизнес-логика — untouched. |
| 7 | **No route changes** | Все URL остаются прежними. |
| 8 | **Accessible contrast** | WCAG AA минимум (4.5:1 для текста). |
| 9 | **Russian terminology** | Все labels, статусы, ошибки — на русском. |
| 10 | **Business-first labels** | Технические термины скрыты или переведены. |
| 11 | **Technical details behind «подробнее»** | UUID, коды, feature flags — в раскрывающихся блоках. |
| 12 | **No backend error dump** | `_safe_error()` — truncate 300 chars, no traceback. |

---

## 6. App Shell Design

```
┌─────────────────────────────────────────────────────┐
│ ██ Header: логотип | user/role | выход               │
├──────────┬──────────────────────────────────────────┤
│ Sidebar  │ Page Header: title + subtitle + actions   │
│          ├──────────────────────────────────────────┤
│ ▸ Продажи│ ┌──────────────┐ ┌──────┐ ┌──────┐      │
│  Кампании│ │ Metric Card  │ │ Card │ │ Card │      │
│  Креативы│ └──────────────┘ └──────┘ └──────┘      │
│          ├──────────────────────────────────────────┤
│ ▸ План-ие│ Section: «Заголовок»                      │
│  План-ие │ ┌──────────────────────────────────────┐ │
│  Бронир. │ │ Table / Detail / Form                 │ │
│          │ └──────────────────────────────────────┘ │
│ ▸ Публик.├──────────────────────────────────────────┤
│  Публик. │ Section: «Заголовок»                      │
│  Пакеты  │ ┌──────────────────────────────────────┐ │
│          │ │ Content                               │ │
│ ▸ Устр-ва│ └──────────────────────────────────────┘ │
│  ...     │                                          │
│          │ Cross-Links Bar                          │
│ ▸ Аналит.│ ┌────┐ ┌────┐ ┌────┐ ┌────┐           │
│  ...     │ │Camp│ │Dev │ │Pkg │ │PoP │           │
│          │ └────┘ └────┘ └────┘ └────┘           │
│ ▸ Админ. │                                          │
│  ...     │                                          │
└──────────┴──────────────────────────────────────────┘
```

**Компоненты app shell:**
- **Header:** фиксированный, 48px, логотип + user + выход
- **Sidebar:** 220px, коллапсируемый (опционально), grouped by role
- **Page Header:** title + subtitle + primary action
- **Main content:** padding 24px, scrollable
- **Cross-links bar:** внизу страницы, горизонтальный набор кнопок-ссылок

---

## 7. RBAC-Aware Navigation Design

### Группировка меню

```
Продажи
├── 📊 Главный экран        → campaigns.read
├── 📢 Кампании             → campaigns.read
├── 🎨 Креативы             → media.read
├── 📝 Согласования         → campaigns.approve

Планирование и бронирование
├── 📋 Планирование         → planning.read
├── 📅 Бронирования         → bookings.read
├── 🗓 Расписание           → scheduling.read

Публикация
├── 📋 Публикации           → publications.read
├── 📜 Пакеты показа        → publications.read

Устройства
├── 🖥️ Устройства           → devices.read
├── 📡 Панель КСО           → devices.gateway.read
├── 🧭 Готовность           → devices.gateway.read
├── 🚀 Развёртывание        → campaigns.read

Аналитика
├── 📈 Отчёты               → reports.read
├── 📊 Аналитика показов    → reports.read
├── ✅ Фактические показы    → reports.read

Администрирование
├── ⏱ Рекламное время       → inventory.read (если есть)
├── 🏪 Магазины             → organization.read
├── ⚙️ Администрирование    → users.read + roles.read
├── 🚨 Аварийное управление → emergency.read

Сервис
├── 📖 Как пользоваться     → public
└── 📜 Соответствие         → public
```

### Правила отображения nav links

- Пункт показывается **только если** у пользователя есть требуемый permission
- `device_service` видит только «Устройства» + «Аналитика» (если `reports.read`)
- Публичные страницы (help, compliance) видны всем
- Разделы без видимых пунктов — скрываются целиком

### Реализация

Шаблон `base.html` получает `current_user_permissions` из контекста (передаётся из route handler). Каждый nav-элемент обёрнут в `{% if 'permission' in permissions %}`.

---

## 8. Component Library Proposal

### 8.1 Page Header

```html
<div class="page-header">
  <div class="page-header-left">
    <h1 class="page-title">Планирование рекламного времени</h1>
    <p class="page-subtitle">Доступность, занятость и конфликты рекламных блоков</p>
  </div>
  <div class="page-header-actions">
    <a href="/planning?..." class="btn btn-secondary btn-sm">Обновить</a>
  </div>
</div>
```

CSS: `.page-header` — flex row, `justify-content: space-between`, `align-items: center`, `margin-bottom: 24px`.

### 8.2 Metric Card

```html
<div class="metric-grid">
  <div class="metric-card">
    <div class="metric-label">Доступно блоков</div>
    <div class="metric-value">142</div>
    <div class="metric-hint">из 200 всего</div>
  </div>
  <div class="metric-card metric-warning">
    <div class="metric-label">Конфликтов</div>
    <div class="metric-value">3</div>
    <div class="metric-hint">требуют внимания</div>
  </div>
</div>
```

CSS: `.metric-grid` — CSS Grid, `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`. `.metric-card` — `background: var(--color-surface)`, `border: 1px solid var(--color-border)`, `border-radius: var(--radius)`, `padding: 16px`. `.metric-value` — крупный шрифт (24px, bold). `.metric-label` — мелкий серый. Цветовые варианты: `metric-success`, `metric-warning`, `metric-error`.

### 8.3 Section Card

Существующий `.section-card` сохраняется и стандартизируется:

```html
<div class="section-card">
  <div class="section-card-header">
    <span class="section-card-icon">📊</span>
    <span class="section-card-title">Доступность</span>
  </div>
  <div class="section-card-body">...</div>
  <div class="section-card-footer">...</div>
</div>
```

Добавить варианты: `.section-card-highlight` (акцентная рамка primary), `.section-card-compact` (меньше padding).

### 8.4 Status Badge (расширенный)

| Статус | CSS класс | Цвет |
|--------|-----------|------|
| Черновик | `status-badge-draft` | muted |
| На согласовании | `status-badge-in_review` | warning |
| Одобрена | `status-badge-approved` | success |
| Отклонена | `status-badge-rejected` | error |
| Активна | `status-badge-active` | success |
| Зарезервировано | `status-badge-reserved` | info |
| Подтверждено | `status-badge-confirmed` | success |
| Опубликовано | `status-badge-published` | success |
| Отменено | `status-badge-cancelled` | muted |
| Ошибка | `status-badge-error` | error |
| Отключено | `status-badge-disabled` | muted |
| Пакет готов | `status-badge-manifest_generated` | info |
| Обслужено КСО | `status-badge-served` | success |
| Нет манифеста | `status-badge-no_manifest` | warning |

### 8.5 Alert / Banner (унифицированный)

```html
<div class="alert alert-success">
  <span class="alert-icon">✅</span>
  <div class="alert-body">
    <div class="alert-title">Успешно</div>
    <div class="alert-text">Бронирование подтверждено.</div>
  </div>
</div>
```

Варианты: `alert-info`, `alert-success`, `alert-warning`, `alert-error`, `alert-feature-flag` (для отключённых feature flags), `alert-backend-unavailable`.

### 8.6 Empty State (улучшенный)

```html
<div class="empty-state">
  <div class="empty-state-icon">📋</div>
  <div class="empty-state-title">Нет бронирований</div>
  <div class="empty-state-text">
    Бронирования создаются после планирования рекламного времени.
    Перейдите в планирование для создания первого бронирования.
  </div>
  <div class="empty-state-action">
    <a href="/planning" class="btn btn-primary">Перейти к планированию</a>
  </div>
</div>
```

### 8.7 Table (стандартизированный)

```html
<table class="table-standard">
  <thead>
    <tr>
      <th>Кампания</th>
      <th class="col-status">Статус</th>
      <th class="col-date">Создана</th>
      <th class="col-actions">Действия</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="/campaigns/CAMP-001" class="table-link">Кампания 1</a></td>
      <td><span class="status-badge status-badge-approved">Одобрена</span></td>
      <td class="text-muted">12.06.2026</td>
      <td class="cell-actions">
        <a href="/campaigns/CAMP-001" class="btn btn-sm btn-ghost">Открыть</a>
      </td>
    </tr>
  </tbody>
</table>
```

CSS: `.table-standard` — `width: 100%`, `border-collapse: collapse`. `thead th` — `position: sticky; top: 0`, `background: var(--color-bg)`. `.col-status` — `width: 120px`. `.col-actions` — `width: 100px`. `.col-date` — `width: 100px`. Пустая таблица: `<tr class="table-empty"><td colspan="N">Нет данных</td></tr>`.

### 8.8 Form (унифицированный)

```html
<form class="form-standard" method="post">
  <div class="form-grid">
    <div class="form-field">
      <label class="form-label">Название <span class="form-required">*</span></label>
      <input type="text" name="name" class="form-control" required>
      <span class="form-hint">Краткое название кампании</span>
    </div>
    <div class="form-field">
      <label class="form-label">Дата начала</label>
      <input type="date" name="date_from" class="form-control">
    </div>
  </div>
  <div class="form-field form-error">
    <span class="form-error-text">Название обязательно для заполнения</span>
  </div>
  <div class="form-actions">
    <button type="submit" class="btn btn-primary">Создать</button>
    <a href="/campaigns" class="btn btn-ghost">Отмена</a>
  </div>
</form>
```

CSS: `.form-grid` — `display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px`. `.form-control` — `width: 100%; padding: 8px 12px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: var(--radius-sm); color: var(--color-text)`. `.form-actions` — `display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px`.

### 8.9 Workflow / Progress

```html
<div class="workflow-checklist">
  <div class="workflow-step done">
    <span class="workflow-step-num">1</span>
    <span class="workflow-step-label">Кампания создана</span>
  </div>
  <div class="workflow-step done">
    <span class="workflow-step-num">2</span>
    <span class="workflow-step-label">Креатив загружен</span>
  </div>
  <div class="workflow-step current">
    <span class="workflow-step-num">3</span>
    <span class="workflow-step-label">Размещение создано</span>
  </div>
  <div class="workflow-step">
    <span class="workflow-step-num">4</span>
    <span class="workflow-step-label">Согласование</span>
  </div>
  ...
</div>
<div class="workflow-progress">
  <div class="workflow-progress-bar">
    <div class="workflow-progress-fill" style="width: 33%"></div>
  </div>
  <span class="workflow-progress-text">3 из 9 шагов</span>
</div>
```

CSS: `.workflow-step` — вертикальный или горизонтальный flex. `.done` — зелёная иконка ✓. `.current` — primary-рамка. `.workflow-progress-bar` — `height: 6px`, `background: var(--color-surface-hover)`. `.workflow-progress-fill` — `background: var(--color-primary)`, transition ширинs.

### 8.10 Cross-Links Bar

```html
<div class="crosslinks-bar">
  <span class="crosslinks-label">Связанные разделы:</span>
  <a href="/campaigns/CAMP-001" class="btn btn-sm btn-ghost">📢 Кампания</a>
  <a href="/devices?code=DEV-001" class="btn btn-sm btn-ghost">🖥️ Устройство</a>
  <a href="/packages/MAN-001" class="btn btn-sm btn-ghost">📜 Пакет показа</a>
</div>
```

CSS: `.crosslinks-bar` — горизонтальный flex, `gap: 8px`, `padding: 12px 0`, `border-top: 1px solid var(--color-border)`.

---

## 9. Status Badge System

Все статусы унифицируются в pill-бейджи:

```css
.status-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: var(--radius-pill);
  font-size: 11px; font-weight: 600;
}
```

### Mapping статусов

| Backend status | Русский label | CSS class |
|---------------|---------------|-----------|
| `draft` | Черновик | `status-badge-draft` |
| `in_review` / `pending` | На согласовании | `status-badge-in_review` |
| `approved` | Одобрена | `status-badge-approved` |
| `rejected` | Отклонена | `status-badge-rejected` |
| `active` | Активна | `status-badge-active` |
| `reserved` | Зарезервировано | `status-badge-reserved` |
| `confirmed` | Подтверждено | `status-badge-confirmed` |
| `published` | Опубликовано | `status-badge-published` |
| `cancelled` | Отменено | `status-badge-cancelled` |
| `archived` | В архиве | `status-badge-archived` |
| `error` | Ошибка | `status-badge-error` |
| `disabled` | Отключено | `status-badge-disabled` |
| `blocked` | Заблокировано | `status-badge-blocked` |
| `manifest_generated` | Пакет готов | `status-badge-manifest_generated` |
| `served` | Обслужено КСО | `status-badge-served` |
| `no_manifest` | Нет пакета | `status-badge-no_manifest` |

---

## 10. Alert / Error / Empty State System

### Alert types

| Type | Use case | Icon |
|------|----------|------|
| `alert-info` | Информация, подсказка | ℹ️ |
| `alert-success` | Действие выполнено | ✅ |
| `alert-warning` | Требует внимания | ⚠️ |
| `alert-error` | Ошибка | ❌ |
| `alert-feature-flag` | Функция отключена | 🔒 |
| `alert-backend-unavailable` | Сервер недоступен | 🔌 |

### Empty states

| Page | Empty title | Empty text | Action |
|------|-------------|------------|--------|
| `/campaigns` | Нет кампаний | Создайте первую кампанию… | Создать кампанию |
| `/bookings` | Нет бронирований | Перейдите в планирование… | Перейти к планированию |
| `/publications` | Нет публикаций | Подготовьте публикационный пакет… | Перейти к кампаниям |
| `/packages` | Нет пакетов показа | Включите генерацию манифестов… | Перейти к публикациям |
| `/planning` | Выберите даты | Укажите период для отображения… | — |
| `/reports/analytics` | Нет данных | Показы не зафиксированы… | Перейти к устройствам |
| `/proof-of-play` | Нет подтверждений | КСО ещё не отправлял данные… | Перейти к устройствам |
| `/devices` | Нет устройств | Добавьте устройства через панель КСО | Панель КСО |

---

## 11. Form Design Standard

- Все формы: `.form-standard` с `.form-grid`
- Метки: над полем, с обязательным `*`
- Поля: `.form-control` — единый стиль для input/select/textarea
- Подсказки: `.form-hint` под полем
- Ошибки: `.form-error` с `.form-error-text` под полем
- Кнопки: `.form-actions` справа
- Primary action: `.btn-primary`, Secondary: `.btn-ghost`, Destructive: `.btn-danger`

---

## 12. Table Design Standard

- Все таблицы: `.table-standard`
- Sticky header: `position: sticky; top: 0`
- Статус-колонка: фиксированная ширина 120px
- Действия-колонка: фиксированная ширина 100px, кнопки `.btn-sm.btn-ghost`
- Пустая таблица: `.table-empty` row
- Плотность: `padding: 8px 12px` для ячеек
- Hover: `.table-standard tbody tr:hover { background: var(--color-surface-hover) }`

---

## 13. Workflow / Progress Design

- Workflow checklist: вертикальный список шагов с иконками
- Шаг: номер + label + статус (done/current/pending)
- Done: зелёная галочка, зелёная рамка
- Current: primary-рамка, жирный текст
- Pending: muted
- Progress bar: узкая полоса (6px) над чеkлистом
- Next action: выделенный блок с баннером + стрелкой

---

## 14. Cross-Link Design

- Расположение: внизу страницы, после основного контента
- Стиль: горизонтальный flex, разделённые кнопки-ссылки
- Без прав: ссылка заменяется на `<span>` без href (plain text)
- Без данных: не показывается (нет ссылки на несуществующий объект)

---

## 15. Russian Terminology Standard

| Технический термин | Русский label (для UI) |
|-------------------|----------------------|
| Campaign | Кампания |
| Creative | Креатив |
| Booking | Бронирование |
| Publication | Публикация |
| GeneratedManifest | **НЕ показывать** → Пакет показа |
| Package | Пакет показа |
| Device | Устройство |
| Display Surface | Экран |
| PoP (Proof of Play) | Подтверждение показа |
| Availability | Доступность |
| Occupancy | Занятость |
| Conflict | Конфликт |
| Feature flag | Технический переключатель (не показывать бизнесу) |
| Capacity Rule | Правило ёмкости |
| Inventory Unit | Рекламный блок |
| Logical Carrier | Носитель |
| Placement | Размещение |
| Placement Target | Цель размещения |
| Advertiser | Рекламодатель |

**Правила:**
- Никогда не показывать «GeneratedManifest» в UI — только «Пакет показа»
- «Feature flag» → «Функция временно отключена» (без технических деталей)
- UUID/коды показывать компактно в `<code>` или за «подробнее»

---

## 16. Page Redesign Priorities

### Priority 1 — Business-Critical (UI.1.3–1.4)

| # | Page | Current state | Target |
|---|------|--------------|--------|
| 1 | Dashboard | Базовая статистика | Metric cards, KPI grid, быстрые действия |
| 2 | Campaigns list | Таблица | Standard table, status badges, фильтры |
| 3 | Campaign detail | Section cards | Workflow checklist, progress, cross-links |
| 4 | Campaign create | Форма | Unified form, field grouping, validation |
| 5 | Planning | Сырая форма + таблицы | Page header, metric cards, section cards, unified tables |
| 6 | Bookings | Форма + таблица | Unified form, status badges, action buttons |
| 7 | Publications | Таблица + actions | Standard table, publish result card, status |
| 8 | Packages | Таблица + KSO check | Standard table, KSO status, cross-links |

### Priority 2 — Operational (UI.1.5)

| # | Page | Target |
|---|------|--------|
| 9 | Devices | Standard table, device status badges |
| 10 | Device Dashboard | Metric cards, readiness badges |
| 11 | Proof of Play | Standard table, campaign/device links |
| 12 | Reports / Analytics | Metric cards, breakdowns, cross-links |
| 13 | Inventory | Standard table, occupancy bars |
| 14 | Schedule | Standard table, timeline |

### Priority 3 — Admin / Support (UI.1.6)

| # | Page | Target |
|---|------|--------|
| 15 | Creatives | Standard table, preview thumbnails |
| 16 | Approvals | Standard table, approve/reject actions |
| 17 | Admin | Metric cards, user/role tables |
| 18 | Emergency | Alerts, dry-run banners |
| 19 | Readiness | Standard table, readiness badges |
| 20 | Deployment | Standard cards |
| 21 | Help / Compliance | Текст — не требует redesign |

---

## 17. UI.1 Split

```
UI.1.0 — Design Gate (этот документ)
├── UI.1.1 — Design System Foundation
│   ├── CSS cleanup: удалить дубли, заполнить пустые секции
│   ├── Design tokens expansion (новые цвета, spacing)
│   ├── Component base CSS: все 10 компонентов
│   └── No template changes — только CSS
│
├── UI.1.2 — App Shell / Navigation / RBAC-aware Sidebar
│   ├── RBAC-aware sidebar: скрытие пунктов по permissions
│   ├── Группировка меню по 6 секциям
│   ├── Page Header компонент на всех страницах
│   └── device_service: только устройства + аналитика
│
├── UI.1.3 — Sales Pages Redesign (Priority 1)
│   ├── Dashboard: metric cards grid
│   ├── Campaigns list: standard table
│   ├── Campaign detail: workflow + cross-links
│   └── Campaign create: unified form
│
├── UI.1.4 — Planning / Booking / Publication / Packages (Priority 1)
│   ├── Planning: metric cards + section cards + unified tables
│   ├── Bookings: unified form + status badges + action buttons
│   ├── Publications: standard table + publish result
│   └── Packages: standard table + KSO status
│
├── UI.1.5 — Analytics / Devices / PoP (Priority 2)
│   ├── Analytics: metric cards + breakdowns + cross-links
│   ├── Devices: standard table + status badges
│   ├── Device Dashboard: readiness badges
│   └── PoP: standard table + links
│
├── UI.1.6 — Admin / Support Pages Cleanup (Priority 3)
│   ├── Creatives / Approvals / Admin / Emergency / Readiness
│   └── Минимальные правки: таблицы, бейджи, единый стиль
│
├── UI.1.7 — UI Security / Regression Gate
│   ├── No secrets, no CDN, no scripts
│   ├── RBAC-aware nav tests
│   ├── Component rendering tests
│   └── Regression: все PORTAL.1 + UI.1 тесты
│
└── UI.1.8 — UI Closure / Business Demo Readiness Gate
    ├── Финальный аудит: визуальный + UX
    ├── Business demo checklist
    └── GO/NO-GO for E2E.1
```

---

## 18. Security / No-Secrets Rules

UI redesign **не должен нарушить**:

| # | Правило | Проверка |
|---|---------|----------|
| 1 | Нет secrets в HTML | grep на Authorization/Cookie/token/password/api_key |
| 2 | Нет traceback | `_safe_error()` всегда |
| 3 | Нет raw JSON как UI | Никаких `json.dumps` в шаблонах |
| 4 | Нет localStorage | Никаких `<script>` с localStorage |
| 5 | Нет CDN | Все ресурсы локальные (`/static/`) |
| 6 | Нет JS framework | Только HTML + CSS |
| 7 | Нет `\| safe` на backend-данных | Только sanitize-фильтры |
| 8 | Нет прямого backend error dump | Всегда через `_safe_error()` |
| 9 | RBAC guards не меняются | `require_auth_for_page` untouched |
| 10 | Нет новых cookies/tokens | Только httpOnly session cookie |

---

## 19. Testing Strategy

### UI.1.1 — CSS-only (no template changes)
- CSS validation: нет дублей, все используемые классы определены
- No regression: существующие тесты pass

### UI.1.2 — App Shell
- RBAC-aware sidebar: тест на скрытие/показ пунктов
- device_service: видит только Устройства + Аналитика
- Page header рендерится на всех страницах

### UI.1.3–1.6 — Page Redesign
- Snapshot-like tests: проверка структуры HTML (заголовки, секции, таблицы)
- No-secrets tests: каждая страница
- Component rendering: каждый компонент на каждой странице
- Status badge rendering: все статусы
- Empty state rendering: все страницы
- Backend error rendering: 403/422/unavailable

### UI.1.7 — Security Gate
- Полный no-secrets скан всех templates
- RBAC nav: все permission-комбинации
- Regression: все PORTAL.1 targeted + portal regression

### UI.1.8 — Closure
- Визуальный аудит: каждый компонент на каждой странице
- Business demo checklist: 10 пунктов
- Regression: полный прогон

---

## 20. Out of Scope

| Item | Reason |
|------|--------|
| Мобильная версия | Не требуется для бизнес-демо |
| JS interactivity | SSR-only constraint |
| Анимации / transitions | Можно добавить в CSS, но без JS |
| Dark/light theme toggle | Только dark theme |
| i18n (многоязычность) | Только русский |
| Печатные стили | Не требуется |
| Accessibility audit (WCAG полный) | Базовый контраст — да, полный аудит — нет |

---

## 21. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| CSS regression: новый CSS ломает старые страницы | HIGH | Поэтапный rollout (1.1→1.2→...), regression каждый шаг |
| RBAC-aware nav: ошибка скрывает нужный пункт | MEDIUM | Тесты на каждую роль |
| Не все страницы получат redesign (admin/support) | LOW | Priority 3 — минимальные правки, не блокирует демо |
| Дизайн-система требует итераций | MEDIUM | CSS-only, легко править |

---

## 22. GO/NO-GO

**✅ GO: UI.1.1 — Design System Foundation**

Условия:
- CSS cleanup: удалить дубли `.btn-sm`, `.btn-primary`, `.btn-success`, `.btn-danger`
- Заполнить пустые секции: forms, tables, status badges, alerts, empty states
- Добавить недостающие компоненты: page-header, metric-card, crosslinks-bar
- Добавить недостающие статусы: reserved, confirmed, served, no_manifest, error, disabled
- Добавить `banner-success`, `banner-warning`, `banner-error`
- 0 template changes на этом шаге
- Regression: 1337/0
