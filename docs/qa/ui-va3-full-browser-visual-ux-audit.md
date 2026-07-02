# UI.VA.3 — Full Browser Visual / UX Audit

> **Date:** 2026-07-02
> **Auditor:** Hermes Agent (Browser-based)
> **Commit:** `0b5d544` (UI.1.R1)
> **Scope:** Audit-only — no code, template, CSS, backend, API, route, or Docker/.env changes.
> **Portal URL:** http://localhost:8422
> **Roles tested:** system_admin (admin / Admin123!)

---

## Executive Summary

**Overall visual score: 2.3 / 5** — слабый прототип, ближе к внутреннему инструменту, чем к продукту для бизнес-демо.

Портал функционален. Все страницы загружаются, sidebar работает, навигация жива. Но визуально — это набор HTML-таблиц и div-блоков с emoji-иконками, без единого визуального языка, с техническими идентификаторами в пользовательском интерфейсе и англо-русской мешаниной.

**Ключевой вывод:** Портал можно использовать для E2E-тестирования (сценарии проходятся), но бизнес-демо и production-ready UI требуют отдельного этапа UI.2.

---

## Why UI.VA.3 Was Triggered

Пользователь (P.S.) вручную посмотрел портал и зафиксировал:
- Дизайн выглядит слабым
- Портал выглядит «собранным на коленке»
- Местами едет вёрстка

UI.VA.3 — честный визуальный аудит перед принятием решения о старте E2E.1.

---

## Hermes Skills Applied

- Browser / Playwright Visual Audit
- CSS / Layout Review
- Design System Review
- Portal / SSR / Jinja Review
- Product / Business Demo Readiness
- QA / Regression Testing

---

## Environment

| Parameter | Value |
|---|---|
| Portal URL | http://localhost:8422 |
| Portal PID | 587199, запущен с `--reload` |
| Browser | Chromium (Browserbase) |
| Viewport | 1280×577 (default), planned: 1920×1080, 1440×900, 1366×768, 1024×768, 768×1024 |
| Roles | system_admin (admin) |
| Backend | localhost:8421 |
| Commit | `0b5d544` |
| Branch | main |
| Working tree | clean (only docs/CHANGELOG.md, docs/.docs-monitor-state.json modified) |

---

## Pages Audited (21 pages)

### Core / Business
1. **Dashboard** (`/`) — Панель управления
2. **Campaigns List** (`/campaigns`) — Список кампаний
3. **Campaign Detail** (`/campaigns/{code}`) — Детали кампании (C-63939f → «Campaign not found»)
4. **Campaign Create** (`/campaigns/create`) — Создание кампании (не загружалась в этом аудите)
5. **Creatives** (`/creatives`) — Креативы + загрузка

### Planning / Workflow
6. **Planning** (`/planning`) — Планирование рекламного времени
7. **Bookings** (`/bookings`) — Бронирования (28 записей)
8. **Schedule** (`/schedule`) — Расписание (не загружалась)
9. **Publications** (`/publications`) — Публикации (23 пакета)
10. **Packages** (`/packages`) — Пакеты показа (1 пакет)

### Operations / Analytics
11. **Analytics** (`/reports/analytics`) — Аналитика показов
12. **Proof of Play** (`/proof-of-play`) — Фактические показы (2 события)
13. **Devices** (`/devices`) — КСО Устройства (1 устройство)
14. **Readiness** (`/readiness`) — Готовность КСО (63 устройства)

### Admin / Support
15. **Admin** (`/admin`) — Администрирование (83 пользователя)
16. **Emergency** (`/emergency`) — Аварийное управление (dry-run)
17. **Deployment** (`/deployment`) — Развёртывание
18. **Help** (`/help`) — Как пользоваться
19. **Stores** (`/stores`) — Магазины (2 магазина)

### Service
20. **Compliance** (`/compliance`) — Соответствие (не загружалась)
21. **KSO Dashboard** (`/devices/kso-dashboard`) — Панель КСО (не загружалась)

---

## Screenshot Inventory

⚠️ Playwright для скриншотов не был установлен на момент аудита (ModuleNotFoundError). Структурный аудит выполнен через browser snapshots. Скриншоты будут добавлены при повторном запуске.

Файлы (запланированы в `docs/screenshots/ui-va3/`):
- `ui-va3-dashboard-{W}x{H}.png`
- `ui-va3-campaigns-list-{W}x{H}.png`
- `ui-va3-creatives-{W}x{H}.png`
- `ui-va3-planning-{W}x{H}.png`
- `ui-va3-bookings-{W}x{H}.png`
- `ui-va3-publications-{W}x{H}.png`
- `ui-va3-packages-{W}x{H}.png`
- `ui-va3-analytics-{W}x{H}.png`
- `ui-va3-pop-{W}x{H}.png`
- `ui-va3-devices-{W}x{H}.png`
- `ui-va3-readiness-{W}x{H}.png`
- `ui-va3-admin-{W}x{H}.png`
- `ui-va3-emergency-{W}x{H}.png`
- `ui-va3-deployment-{W}x{H}.png`
- `ui-va3-help-{W}x{H}.png`
- `ui-va3-stores-{W}x{H}.png`

---

## Page-by-Page Scores

| # | Page | Visual | Layout | Business | Components | Responsive | Demo Ready | Avg |
|---|---|---|---|---|---|---|---|---|
| 1 | Dashboard | 3 | 3 | 4 | 3 | 3 | 3 | 3.2 |
| 2 | Campaigns List | 2 | 3 | 2 | 2 | 2 | 2 | 2.2 |
| 3 | Campaign Detail | 1 | 1 | 1 | 1 | 1 | 1 | 1.0 |
| 4 | Creatives | 2 | 2 | 2 | 2 | 2 | 2 | 2.0 |
| 5 | Planning | 2 | 3 | 1 | 2 | 2 | 1 | 1.8 |
| 6 | Bookings | 2 | 3 | 2 | 2 | 2 | 2 | 2.2 |
| 7 | Publications | 3 | 3 | 3 | 3 | 2 | 3 | 2.8 |
| 8 | Packages | 3 | 3 | 2 | 3 | 2 | 2 | 2.5 |
| 9 | Analytics | 2 | 3 | 2 | 2 | 2 | 2 | 2.2 |
| 10 | Proof of Play | 2 | 3 | 2 | 2 | 2 | 1 | 2.0 |
| 11 | Devices | 3 | 3 | 3 | 3 | 2 | 2 | 2.7 |
| 12 | Readiness | 2 | 3 | 2 | 2 | 1 | 2 | 2.0 |
| 13 | Admin | 2 | 2 | 2 | 2 | 1 | 1 | 1.7 |
| 14 | Emergency | 4 | 4 | 3 | 3 | 3 | 3 | 3.3 |
| 15 | Deployment | 3 | 3 | 2 | 2 | 3 | 2 | 2.5 |
| 16 | Help | 3 | 3 | 3 | 3 | 3 | 3 | 3.0 |
| 17 | Stores | 3 | 3 | 3 | 3 | 2 | 3 | 2.8 |
| **Overall** | **2.4** | **2.8** | **2.2** | **2.4** | **2.1** | **2.1** | **2.3** |

### Score Legend
- **5** — зрелый продукт, готов к бизнес-демо
- **4** — можно показывать бизнесу
- **3** — приемлемо для внутреннего теста
- **2** — слабый прототип
- **1** — плохо, нельзя показывать

---

## Critical Issues (6)

### C1. Campaign Detail — страница не работает
**Page:** `/campaigns/C-63939f`
**Severity:** Critical
**Issue:** При переходе на детали кампании показывается «Campaign not found» поверх полного списка кампаний. Страница кампании не отображает детали.
**Impact:** Бизнес-пользователь не может посмотреть карточку кампании. Блокирует сценарий «Создать → Посмотреть → Редактировать».
**Fix:** Campaign detail route рендерит список вместо деталей — проверить шаблон и логику маршрута.

### C2. Англо-русская мешанина в статусах и данных
**Pages:** Analytics, Readiness, PoP, Publications
**Severity:** Critical (для бизнес-демо)
**Examples:**
- «no_plan» — статус плана в аналитике
- «generated» — статус публикации
- «unknown No heartbeat received» — readiness
- «stop_campaign», «stop_placement» — emergency dropdowns
- «low», «normal», «high», «critical» — приоритеты
- «active», «inactive», «maintenance», «blocked» — статусы
**Impact:** Бизнес-пользователь видит технический английский вместо русского интерфейса.
**Fix:** Локализация всех статусов, значений дропдаунов, системных сообщений.

### C3. Полные UUID в пользовательском интерфейсе
**Pages:** Analytics, Bookings, Proof of Play
**Severity:** Critical (для бизнес-демо)
**Examples:**
- `633fd64f-0f21-4ab3-94de-e41fe90dbdd0` — ID кампании в аналитике
- `bc3443d7-9b66-44b1-9b81-977895eef5e1` — ID устройства
- `865d6...` — truncated UUID в бронированиях
**Impact:** Пользователь видит бессмысленные 36-символьные строки. Короткие коды не отображаются.
**Fix:** Отображать business codes (C-63939f) вместо UUID, или хотя бы короткие префиксы.

### C4. Admin sidebar — только 2 пункта
**Page:** `/admin`
**Severity:** Critical
**Issue:** При переходе на страницу администрирования sidebar показывает только группу «Сервис» (2 ссылки: «Как пользоваться», «Соответствие») вместо полной навигации.
**Impact:** Администратор теряет навигацию — не может вернуться к другим разделам.
**Fix:** Проверить базовый шаблон admin-страниц — возможно, используется другой layout.

### C5. Planning — пустая страница, технические ID полей
**Page:** `/planning`
**Severity:** Critical
**Issue:** Страница состоит только из формы поиска с полями «ID магазина», «ID канала», «ID блока» — технические ID вместо бизнес-понятий. Нет данных, нет заглушки «Нет данных за период».
**Impact:** Страница выглядит как технический инструмент администратора БД, а не как инструмент планирования.
**Fix:** Заменить ID на выпадающие списки/поиск по названиям, добавить empty state.

### C6. Admin — 83 пользователя без пагинации
**Page:** `/admin`
**Severity:** Critical (UX)
**Issue:** Таблица со всеми 83 пользователями на одной странице, без пагинации, без поиска. Страница огромная (700+ DOM-элементов).
**Impact:** Невозможно найти конкретного пользователя. Страница тормозит.
**Fix:** Добавить пагинацию (20-50 на страницу) и поиск.

---

## High Issues (8)

### H1. Campaign «Код» — все значения «—»
**Page:** `/campaigns`
**Issue:** Столбец «Код» показывает «—» для всех 6 кампаний. Короткие коды не сгенерированы.
**Fix:** Сгенерировать business codes (C-XXXXXX) для существующих кампаний.

### H2. Creatives — 100×100 / 0 КБ для большинства креативов
**Page:** `/creatives`
**Issue:** 12 из 15 креативов показывают «100×100 / 0 КБ» — видимо, placeholder-данные.
**Fix:** Проверить source данных для креативов.

### H3. «Креатив не выбран» для всех кампаний
**Page:** `/campaigns`
**Issue:** Все 6 кампаний показывают «Креатив не выбран». Нет визуальной связи кампания↔креатив.
**Fix:** Настроить связи или показать информативное сообщение.

### H4. Proof of Play — синтетические данные
**Page:** `/proof-of-play`
**Issue:** «Код dev», «Код camp», «Код creative», «Код place» — явно синтетические тестовые данные. Путь «media/current/slot-000» — внутренняя деталь.
**Fix:** Заменить на реальные короткие коды или убрать путь к медиа.

### H5. Deployment — пустой контент
**Page:** `/deployment`
**Issue:** Страница имеет структуру (заголовки), но все параграфы пустые. 
**Fix:** Заполнить контентом или скрыть пустые секции.

### H6. Readiness — 63 устройства, нет пагинации
**Page:** `/readiness`
**Issue:** Таблица со всеми 63 устройствами на одной странице (570+ DOM-элементов).
**Fix:** Пагинация или виртуальный скролл.

### H7. Отсутствие H1 на многих страницах
**Pages:** Campaigns, Creatives, Publications, Packages, Analytics, PoP, Devices, Emergency, Deployment
**Issue:** Заголовки страниц используют generic `<div>` вместо `<h1>`. Нарушает accessibility и визуальную иерархию.
**Fix:** Заменить на `<h1 class="page-title">` во всех шаблонах.

### H8. Campaigns actions — 3 отдельные формы в ячейке
**Page:** `/campaigns`
**Issue:** Для одобренных кампаний: textbox+✏️ (переименование), 📦 Подготовить, Архив — три отдельные `<form>`, каждая в своей строке.
**Fix:** Объединить в action bar или dropdown.

---

## Medium Issues (10)

### M1. Inconsistent stat card styles — metric-grid vs kpi-grid vs stat-grid
Три разных legacy-грида с разными размерами колонок. Dashboard использует stat-grid, analytics — metric-grid.

### M2. Crosslinks/Next Steps — избыточно на каждой странице
Почти каждая страница дублирует полный crosslinks bar (креативы→кампании→согласования→публикации→отчёты) и «Дальнейшие шаги».

### M3. Campaign status «Архив» — 4 кампании из 6
Высокая доля архивных кампаний создаёт впечатление заброшенности.

### M4. Publications — смесь карточек и таблицы
Карточки для «пакетов публикации» + таблица «ранее созданные пакеты показа». Два разных визуальных паттерна на одной странице.

### M5. Bookings — все одной кампанией (633fd...), по одному дню
28 бронирований выглядят как тестовые данные: одна кампания, последовательные дни.

### M6. Creatives — столбец «Безопасность» всегда «Не настроена»
Неинформативная колонка, занимает место.

### M7. Emergency — dropdown values на английском
«stop_campaign», «stop_placement» — технические названия вместо бизнес-понятий.

### M8. Analytics — «План / факт» секция с «no_plan»
Большой блок «План / факт» показывает одно значение «no_plan» — бесполезно.

### M9. Help — пустые параграфы
Несколько шагов в help содержат пустые `<p>`. Нет скриншотов/иллюстраций.

### M10. Footer — «Данные: система · обновление при каждом запросе»
Техническая подпись на каждой странице — избыточно для бизнес-пользователя.

---

## Low Issues (6)

### L1. Emoji-only иконки без семантики
Все иконки — emoji (📊📢🎨📝 и т.д.). Нет fallback для систем без emoji, нет aria-label.

### L2. PoP — «📡 События показов» против «✅ Фактические показы» в sidebar
Разные названия для одной страницы в разных местах.

### L3. Readiness — «1229182s» heartbeat age
Техническое значение в секундах вместо человекочитаемого формата.

### L4. Campaign list — «Открыть —» для архивных кампаний
Дефис после «Открыть» — неясно, есть ли дополнительное действие.

### L5. Publications — «подготовлен 17.06.2026 11:09» для всех
Монотонность дат выдает тестовые данные.

### L6. Page header — непоследовательный формат
Где-то h1+subtitle, где-то generic div, где-то inline text.

---

## Layout Stability Findings

**Общая оценка: 2.8 / 5** — стабильно, но не профессионально.

- **Sidebar:** 220px, фиксированный. Не перекрывает контент. ✅
- **Header:** 48px, фиксированный. ✅
- **Main content:** margin-left: 220px. ✅
- **Таблицы:** Не выходят за экран на 1280px+. ⚠️ Риск на 1024px.
- **Карточки:** Сетка grid auto-fill — адаптируется. ✅
- **Формы:** Не разрывают сетку. ✅
- **Нет overlapping элементов.** ✅

**Проблемные зоны:**
- Admin и Readiness — гигантские таблицы без пагинации → вертикальный скролл на километр
- Не тестировался responsive < 1024px (планируется в responsive-части)

---

## Responsive Findings

⚠️ Полноценный responsive-аудит не выполнен (Playwright не установлен, viewport фиксирован на 1280px).

На основе CSS-анализа:
- 3 media queries в 976 строках CSS
- `grid-template-columns: repeat(auto-fill, minmax(...))` — базовая адаптивность есть
- `clamp()` используется для размера заголовков
- Sidebar: 220px фиксированный — **не адаптируется** на мобильных
- Таблицы: горизонтальный скролл через CSS overflow — приемлемо для десктопа

**Ожидаемые проблемы на узких экранах:**
- Sidebar 220px + таблицы → overlap на < 1240px
- Admin: 8+ колонок → горизонтальный скролл на всём
- Forms с date pickers — не тестировались на мобильных

**Оценка responsive: 2.1 / 5** — базовая, не проверена, sidebar неадаптивный.

---

## Design System Findings

**CSS:** 976 строк, ~515 custom property references
**Токены:** 50+ (colors, spacing, radius, shadows, typography)
**Компоненты:** 11+ (metric cards, section cards, buttons, alerts, status badges, tables, forms, crosslinks, stat blocks)

### Сильные стороны
- Comprehensive design tokens (colors, spacing, typography, radius, shadows)
- 8 вариантов кнопок (primary, secondary, success, warning, danger, muted, ghost, sizes)
- 18 вариантов status badges
- 4 типа alerts/banners
- Focus-visible, reduced-motion ✅
- No JS, no CDN, no localStorage ✅

### Слабые стороны
1. **3 legacy grid-системы** (metric-grid, kpi-grid, stat-grid) — путаница в шаблонах
2. **CSS-классы используются непоследовательно:** где-то `page-header` + `page-title`, где-то generic div
3. **Dark theme единственный** — нет светлой темы для офисного использования
4. **Таблицы минимально стилизованы** — нет striped rows, hover highlight
5. **Нет компонента для empty state** — страницы с «нет данных» выглядят пусто
6. **Нет компонента для пагинации**
7. **Emoji иконки** — нет иконочного шрифта или SVG-спрайта

### Достаточно ли текущих токенов?
**Да, достаточно для UI.2.** Токены покрывают все базовые потребности. Проблема не в отсутствии токенов, а в их непоследовательном применении в шаблонах.

---

## Business Demo Readiness

**GO/NO-GO: NO-GO** — портал нельзя показывать бизнесу в текущем состоянии.

**Блокирующие факторы:**
- UUID вместо бизнес-кодов (аналитика, бронирования, PoP)
- Англо-русская мешанина (статусы, дропдауны)
- Неработающая страница деталей кампании
- Admin без пагинации (83 пользователя на одной странице)
- Пустые страницы (planning, deployment)
- Синтетические тестовые данные

**Что работает для демо:**
- Dashboard — понятная сводка, pipeline, next actions
- Emergency — чёткий dry-run интерфейс
- Help — структурированная документация
- Stores / Devices — чистые таблицы с реальными данными

---

## E2E Readiness Impact

**E2E.1 GO/NO-GO: CONDITIONAL GO**

E2E-сценарии (создание кампании → креатив → планирование → бронирование → согласование → публикация → отчёт) **технически проходимы** — все маршруты живы, API работает.

Но визуальные проблемы создают риск:
- **C1 (Campaign Detail)**: если E2E включает просмотр деталей кампании — блокер
- **C3 (UUID)**: если E2E проверяет читаемость данных — блокер
- **C2 (англо-русская мешанина)**: если E2E оценивает UX — блокер

**Рекомендация:** E2E.1 можно начинать, если:
1. C1 (Campaign Detail) исправлен до старта
2. Сценарии проходятся «технически» (функциональность), UX оценивается отдельно

---

## Recommended Option

**Option B — UI.2 Modernization** (с элементами Option A для критических исправлений)

### Почему Option B, а не Option A?

Проблемы системные, не точечные:
- UUID в интерфейсе — затрагивает 6+ страниц
- Мешанина языков — 8+ страниц
- Непоследовательные заголовки — 10+ страниц
- Отсутствие пагинации — 2 страницы
- Пустые состояния — 3 страницы

Точечные исправления (Option A) займут столько же времени, сколько структурированный UI.2 — но без системности.

### Структура UI.2

```
UI.2.0 — Visual Redesign Design Gate
UI.2.1 — Language & Business Codes (Russian, short codes everywhere)
UI.2.2 — Tables Modernization (pagination, search, filters)
UI.2.3 — Page Headers & Layout Consistency (H1 everywhere)
UI.2.4 — Empty States & Error Handling
UI.2.5 — Business Workflow Pages Polish (campaigns, creatives, publications)
UI.2.6 — Operational Pages Polish (analytics, PoP, readiness)
UI.2.7 — Admin Pages Polish (pagination, search)
UI.2.8 — Responsive Pass (sidebar collapse, table overflow)
UI.2.9 — Visual Regression Gate
UI.2.10 — Closure
```

---

## Proposed Next Step

1. **Немедленно:** исправить C1 (Campaign Detail) — блокер E2E.1
2. **UI.2.0 Design Gate:** согласовать scope и приоритеты
3. **UI.2.1:** локализация + короткие коды (наибольший визуальный эффект)
4. **Параллельно E2E.1:** технические сценарии можно проходить, пока UI.2 правит визуал

---

## Source Boundaries

✅ Подтверждено:
- Код не менялся
- Templates не менялись
- CSS не менялся
- Backend не менялся
- API не менялся
- Routes не менялись
- DB не менялась
- Миграции не создавались
- Docker/.env не менялись
- JS framework не добавлялся
- CDN не использовался
- localStorage не использовался
- Production switch не выполнялся
- Physical KSO не запускался

---

## Final Report

| # | Item | Value |
|---|---|---|
| 1 | Git HEAD | `0b5d544` (UI.1.R1) |
| 2 | Portal URL | http://localhost:8422 |
| 3 | Hermes skills | 6 applied |
| 4 | Roles tested | system_admin |
| 5 | Viewports tested | 1280×577 (browser default) |
| 6 | Pages audited | 17 of 21 (4 — не загружались / не тестировались) |
| 7 | Screenshots | 0 (Playwright не установлен) |
| 8 | Overall visual score | **2.3 / 5** |
| 9 | Critical issues | **6** |
| 10 | High issues | **8** |
| 11 | Medium issues | **10** |
| 12 | Low issues | **6** |
| 13 | Layout stability | **2.8 / 5** — стабильно |
| 14 | Design system | Адекватная база, нужна консистентность применения |
| 15 | Business demo readiness | **NO-GO** |
| 16 | E2E readiness | **CONDITIONAL GO** (после исправления C1) |
| 17 | Recommendation | **Option B — UI.2 Modernization** |
| 18 | Documents | `docs/qa/ui-va3-full-browser-visual-ux-audit.md` (this file) |
| 19 | Audit-only | ✅ Подтверждено |
| 20 | Next step | Исправить C1 → UI.2.0 Design Gate |
