# Design System Hardening — 43.8

## Overview

Полная переработка визуальной системы портала: тёмная enterprise/SaaS тема, единые компоненты, утилитарные классы, fluid-типографика.

## Что изменено

### 1. CSS (styles.css)

Полностью переписан — ~34 KB структурированного CSS.

**Дизайн-токены:**
- 4 уровня теней: `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-glow`
- Fluid-типографика через `clamp()`: `--text-page-title`, `--text-section-title`, `--text-body`
- Радиусы: `--radius-xs` (4px), `--radius-sm` (6px), `--radius` (8px), `--radius-lg` (12px), `--radius-pill` (100px)

**Система кнопок:**
- `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-danger`, `.btn-success`, `.btn-warning`
- `.btn-sm`, `.btn-lg`, `.btn-block`, `.btn-icon`, `.btn-disabled`
- `:active` — scale(0.98)

**Утилитарные классы:**
- Типографика: `.text-xs`, `.text-sm`, `.text-md`, `.text-muted`, `.text-secondary`, `.text-error`, `.text-warning`, `.text-success`
- Отступы: `.mt-4/8/12/16`, `.mb-8/12/16`, `.mr-8`, `.ml-auto`, `.p-0`, `.px-12`, `.py-8`
- Flex: `.flex-between`, `.flex-center`, `.flex-wrap`, `.inline`, `.inline-flex`
- Формы: `.form-input-sm`, `.form-input-md`, `.form-input-lg`, `.form-input-w140`
- Прогресс: `.fill-0` … `.fill-100`

**Статусы (pill-style):**
- `.status-success`, `.status-warning`, `.status-danger`, `.status-info`, `.status-muted`

**Контентные панели:**
- `.content-card`, `.info-panel`, `.warning-panel`, `.action-panel`, `.note-panel`
- `.section-card-error`, `.section-card-border-success`

**Таблицы:**
- Больше воздуха: `padding: 11px 14px`
- `tbody tr` transition
- `.cell-code`, `.cell-mono`
- `.table-clean` — без границ/теней

**Сайдбар:**
- Убран блок «Этапы (1→5)»
- Утончённые разделители
- Мягкий активный фон `rgba(59,130,246,0.12)`
- Округлённые ссылки

**Motion safety:**
- `@media (prefers-reduced-motion: reduce)` — полное отключение анимаций

### 2. Очистка inline-стилей

- **Было:** 269 inline `style="..."`
- **Стало:** 139 (−48%)
- Большинство оставшихся — динамические Jinja2-выражения, абсолютное позиционирование, кастомные ширины

### 3. Tests

14 новых тестов в `TestDesignSystemHardening`:
- CSS-токены, reduced-motion, fluid-типографика
- Полнота кнопочной системы
- Pill-статусы
- Контентные панели
- fill-N классы
- Spacing/text утилиты
- Аудит inline-стилей (<200)
- Login изоляция
- Sidebar без «Этапы»
- Safety (no JS/CDN/technical labels)

### 4. Regression

- **Portal: 664 passed, 32 skipped, 0 failed**

## Design Decisions

- Тёмная тема сохранена как единственная (enterprise/SaaS dark-first)
- Fluid-типографика через `clamp()` — читаемость на широких мониторах
- Pill-статусы — современный SaaS-стандарт
- Утилитарные классы вместо inline-стилей — поддерживаемость
- `prefers-reduced-motion` — accessibility
