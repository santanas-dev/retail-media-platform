# UI.1.1 — Design System Foundation

**Phase:** UI.1.1 (CSS foundation)  
**Previous:** UI.1.0 — Design Gate (`ea1e191`)  
**Status:** ✅ COMPLETE — GO for UI.1.2  

---

## Что изменено в styles.css

**Файл:** `apps/portal-web/static/styles.css`
- Было: 533 строки, фрагментировано, пустые секции, дубли
- Стало: ~1100 строк, 20 numbered sections, чистый структурированный CSS

### Структура (20 секций)

1. **Design Tokens** — все цвета, spacing, radius, shadows, typography
2. **Reset & Base** — box-sizing, html, body, code, focus-visible, reduced-motion
3. **Layout — App Shell** — header, sidebar, main
4. **Page Header** — .page-header, .page-title, .page-subtitle, .page-actions
5. **Metric Cards** — .metric-grid, .metric-card, + legacy .kpi-*/.stat-*
6. **Section Cards** — .section-card + .content-card
7. **Buttons** — единая система (9 variants), нет дублей
8. **Alerts / Banners** — .alert-*, .banner-*, flash, success/error-banner, info/warning/note-panel
9. **Status Badges** — 15 variants + legacy .status-pill + .badge-* + .readiness-badge
10. **Tables** — .data-table, .table-standard, .table-compact, .table-clean, empty states
11. **Forms** — .form-grid, .form-control, .filter-bar, .filter-toolbar, upload-zone
12. **Empty States** — .empty-state, .empty-state-icon/title/text/action
13. **Workflow / Progress** — .progress-bar, .workflow-progress-bar, .pipeline, .dist-bar, .checklist, .next-action-card
14. **Cross-Links** — .crosslinks-bar, .crosslink, .crosslink-disabled
15. **Detail / Flow / Lifecycle** — .detail-grid, .flow-breadcrumbs, .lifecycle-flow
16. **Supporting Components** — summary-panel, timestamp, hint, help, blocker-grid, misc
17. **Utilities** — margin/padding/gap/flex/text/fill helpers
18. **Login / Auth** — auth-body, auth-card, login-form
19. **Page Specific** — compliance, dashboard, row-detail, status-dot
20. **Responsive** — @media 1024px, @media 768px

---

## Design Tokens

| Категория | Токены |
|-----------|--------|
| Colors | 25 токенов (bg, surface, text, primary, success, warning, error, info, disabled, sidebar) |
| Spacing | 6 токенов (--space-1 → --space-6: 4px → 32px) |
| Radius | 5 токенов (xs 4px, sm 6px, md 8px, lg 12px, pill 100px) |
| Shadows | 4 токена (sm, md, lg, glow) |
| Typography | 16 токенов (font-ui, font-mono, text-xs→2xl, weight-*, leading-*) |

---

## Компоненты (стандартизированы)

| # | Компонент | Классы |
|---|----------|--------|
| 1 | Page Header | `.page-header` `.page-title` `.page-subtitle` `.page-actions` |
| 2 | Section Card | `.section-card` + header/body/footer/badge/error/warning |
| 3 | Metric Card | `.metric-grid` `.metric-card` `.metric-label` `.metric-value` `.metric-hint` |
| 4 | Buttons | 9 variants: primary/secondary/success/warning/danger/muted/ghost + sm/lg/block/disabled |
| 5 | Alerts | 6 types: info/success/warning/error + banner/alert dual system + flash messages |
| 6 | Status Badges | 15 variants: draft/pending/approved/rejected/reserved/confirmed/published/cancelled/blocked/manifest_generated/error/disabled/served/no_manifest/unknown |
| 7 | Tables | `.data-table` `.table-standard` `.table-compact` `.table-clean` + empty states |
| 8 | Forms | `.form-grid` `.form-control` `.form-label` `.form-hint` `.form-error` `.form-actions` + filter-bar/toolbar |
| 9 | Empty States | `.empty-state` + icon/title/text/action |
| 10 | Workflow | `.progress-bar` `.workflow-progress-bar` `.pipeline` `.dist-bar` `.checklist` `.next-action-card` |
| 11 | Cross-Links | `.crosslinks-bar` `.crosslink` `.crosslink-disabled` |

---

## Дубли убраны

| Дубль | Решение |
|-------|---------|
| `.btn-sm` определён дважды (487 и 519) | Оставлен один: `padding: 5px 10px; font-size: var(--text-sm)` |
| `.btn-primary` определён дважды (158 и 521) | Объединён в единый блок (секция 7) |
| `.btn-success` определён дважды (484 и 523) | Объединён |
| `.btn-danger` определён дважды (486 и 525) | Объединён |

---

## Missing classes добавлены

| Класс | Где используется |
|-------|-----------------|
| `.banner-success` | campaigns_detail.html — «Кампания одобрена» |
| `.banner-warning` | templates |
| `.banner-error` | templates |
| `.alert-success` | template conditionals |
| `.alert-warning` | template conditionals |
| `.status-badge-reserved` | bookings workflow |
| `.status-badge-confirmed` | bookings workflow |
| `.status-badge-served` | KSO check |
| `.status-badge-no_manifest` | KSO check |
| `.status-badge-error` | error states |
| `.status-badge-disabled` | feature flag OFF |

---

## Responsive Baseline

- **@1024px:** sidebar 220→180px, grid columns adjust
- **@768px:** sidebar → icons-only (56px), no labels, single-column forms/grids, table font-size reduced

## Accessibility Baseline

- `:focus-visible` — 2px primary outline, 2px offset
- `prefers-reduced-motion` — instant transitions
- `:disabled` — opacity 0.5, no pointer events
- WCAG AA contrast maintained (dark theme)

## Security

- 0 external URL imports
- 0 CDN references (cdn./unpkg./jsdelivr./googleapis.)
- 0 javascript: URLs
- 0 localStorage
- 0 secrets (password/token/api_key) in CSS rules

---

## Tests

| Suite | Tests | Status |
|-------|-------|--------|
| UI.1.1 targeted | 57 | ✅ 57/57 |
| PORTAL.1.1–1.6 targeted | 297 | ✅ 297/297 |
| Portal regression | 1394 | ✅ (20 skipped) |

## GO/NO-GO

**✅ GO: UI.1.2 — App Shell / RBAC-aware Navigation**
