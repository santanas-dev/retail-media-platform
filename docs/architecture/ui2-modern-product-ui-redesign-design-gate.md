# UI.2.0 — Modern Product UI Redesign: Design Gate

> **Date:** 2026-07-02
> **Phase:** UI.2.0 (design gate — no implementation)
> **Commit:** `a702390` (UI.C1.R1)
> **Scope:** Design the UI.2 modernization; no code, template, CSS, backend, or config changes.

---

## Executive Summary

UI.VA.3 evaluated the portal at **2.3 / 5** — a weak prototype, not a product. 30 issues were identified: 6 Critical, 8 High, 10 Medium, 6 Low. C1 (broken campaign detail) was fixed by UI.C1.R1. The remaining 29 issues are systemic: language mixing, full UUIDs as UI labels, missing pagination/page headers, empty pages, and inconsistent components.

UI.2.0 designs the modernization as a structured sequence of 10 implementation steps (UI.2.1–UI.2.10), each with clear scope, deliverables, and test gates. The goal: raise the portal from 2.3 to **≥3.5** — acceptable for business demo — while respecting all source boundaries (no backend/API/DB/Docker changes, no JS framework, no CDN).

**Recommendation:** GO for UI.2.1 (Language & Status Localization) — the highest-impact, lowest-risk quick win.

---

## Why UI.2 Is Needed

1. **Business demo NO-GO** — portal looks like a prototype, not a product
2. **Systemic issues, not bugs** — cannot be fixed with 5–10 patches
3. **Tech debt alignment** — UID-01 through UID-08 in technical-debt-register.md
4. **E2E.1 technically GO but visually weak** — customers would judge the product
5. **C1 fixed proves the approach works** — but UUID links remain as a lingering visual issue

---

## Hermes Skills Applied

- UI / UX Design Review
- Modern SaaS Product Design
- CSS / Layout Architecture
- Design System Review
- Portal / SSR / Jinja Review
- Product / Business Demo Readiness
- QA / Regression Testing
- Security Review
- Documentation / Audit
- Critical Reasoning

---

## Current Baseline

| Metric | Value |
|---|---|
| Overall visual score | 2.3 / 5 |
| C1 targeted tests | 32 passed |
| UI.1 targeted tests | 424 passed |
| Full portal regression | 1802 passed / 34 skipped / 8 errors |
| Backend regression | 2695 / 0 errors |
| Business demo | NO-GO |
| E2E.1 | Technically GO (after C1 fix) |
| Production switch | NO-GO |
| Physical KSO | NO-GO |
| Store pilot | NO-GO |

---

## UI.VA.3 Findings — Status Mapping

### Critical Issues

| ID | Issue | Status | UI.2 Step |
|---|---|---|---|
| C1 | Campaign Detail broken | ✅ **RESOLVED** — UI.C1.R1 | — |
| C2 | Англо-русская мешанина | 🔴 OPEN | UI.2.1 |
| C3 | Полные UUID в UI | 🔴 OPEN | UI.2.2 |
| C4 | Admin sidebar only 2 links | 🔴 OPEN (confirmed 2026-07-02) | UI.2.4 |
| C5 | Planning empty technical page | 🔴 OPEN | UI.2.5 |
| C6 | Admin 83 users without pagination | 🔴 OPEN | UI.2.3 |

### High Issues

| ID | Issue | Status | UI.2 Step |
|---|---|---|---|
| H1 | Campaign code values all "—" | 🟠 OPEN | UI.2.2 |
| H2 | Creatives 100×100 / 0 KB | 🟠 OPEN | UI.2.6 |
| H3 | "Креатив не выбран" for all | 🟠 OPEN | UI.2.6 |
| H4 | PoP synthetic values | 🟠 OPEN | UI.2.7 |
| H5 | Deployment empty content | 🟠 OPEN | UI.2.5 |
| H6 | Readiness 63 devices no pagination | 🟠 OPEN | UI.2.3 |
| H7 | Missing H1 on many pages | 🟠 OPEN | UI.2.4 |
| H8 | Campaigns 3 forms in cell | 🟠 OPEN | UI.2.6 |

### Medium Issues (10)

| ID | Issue | UI.2 Step |
|---|---|---|
| M1 | Inconsistent stat grids (3 legacy) | UI.2.8 |
| M2 | Crosslinks overuse | UI.2.6 |
| M3 | 4/6 campaigns archived | Data (not UI) |
| M4 | Publications mixed cards+table | UI.2.6 |
| M5 | Bookings test-looking data | Data (not UI) |
| M6 | Creatives security column always "Не настроена" | UI.2.6 |
| M7 | Emergency dropdown English values | UI.2.1 |
| M8 | Analytics "no_plan" placeholder | UI.2.1 |
| M9 | Help empty paragraphs | UI.2.5 |
| M10 | Technical footer | UI.2.8 |

### Low Issues (6)

| ID | Issue | UI.2 Step |
|---|---|---|
| L1 | Emoji-only icons | UI.2.8 |
| L2 | PoP inconsistent naming | UI.2.7 |
| L3 | Readiness "1229182s" heartbeat | UI.2.7 |
| L4 | Campaign "Открыть —" trailing dash | UI.2.6 |
| L5 | Publication monotone dates | Data |
| L6 | Inconsistent page headers | UI.2.4 |

---

## Design System Assessment

### What we have (from `styles.css`, 976 lines, ~515 custom properties)

**Strengths:**
- Comprehensive design tokens: 50+ (colors × 5 variants, spacing × 6, radius × 5, shadows × 4, typography × 12)
- 8 button variants + 3 sizes
- 18 status badge variants
- 4 alert/banner types
- Focus-visible + reduced-motion ✅
- No JS, no CDN, no localStorage ✅

**Weaknesses:**
- 3 legacy grid systems (metric-grid, kpi-grid, stat-grid) — confusion in templates
- CSS classes used inconsistently across templates
- No empty-state component
- No pagination component
- No light theme
- Minimal table styling (no striped/hover rows)
- Emoji-dependent icon system

**Verdict:** The design system foundation is adequate for UI.2. The problem is not missing tokens — it's inconsistent application in templates. UI.2 should **extend** the existing system, not replace it.

---

## UI.2 Design Principles

1. **SSR-only, vanilla CSS** — no JS framework, no CDN, no localStorage
2. **Business-first language** — 100% Russian on business pages, English only in code
3. **Short identifiers everywhere** — never a 36-char UUID as primary UI label
4. **Consistent page structure** — H1 + subtitle + primary action on every page
5. **Component reuse** — extend existing design tokens, don't invent new ones
6. **Pagination by default** — any table with >20 rows gets pagination
7. **Empty state, not blank page** — every page with no data shows a helpful message
8. **Safe error handling** — no traceback, no raw JSON, no internal paths
9. **Desktop-first responsive** — 1366px is the minimum supported width
10. **Incremental delivery** — each step is independently testable and committable

---

## Strategy: Language / Localization (UI.2.1)

### Problem
Mixed RU/EN across statuses, dropdown values, backend messages, and data displays.

### Approach
Create a **localization map** — a single Python dict in `apps/portal-web/labels.py`:

```python
STATUS_LABELS = {
    # Campaign
    "draft": "Черновик",
    "in_review": "На согласовании",
    "approved": "Одобрено",
    "rejected": "Отклонено",
    "archived": "Архив",
    "active": "Активна",
    # Publication
    "generated": "Сформирован",
    "published": "Опубликован",
    "cancelled": "Отменён",
    # Device
    "ready": "Готов",
    "warning": "Внимание",
    "blocked": "Заблокирован",
    "unknown": "Не определено",
    # Emergency
    "stop_campaign": "Остановка кампании",
    "stop_placement": "Остановка размещения",
    "stop_channel": "Остановка канала",
    "stop_store": "Остановка магазина",
    "stop_device": "Остановка устройства",
    "emergency_message": "Экстренное сообщение",
    "resume": "Возобновить",
    # Priority
    "low": "Низкий",
    "normal": "Обычный",
    "high": "Высокий",
    "critical": "Критический",
    # Generic
    "no_plan": "Нет данных",
    "no_data": "Нет данных",
    "not_configured": "Не настроена",
}
```

Then use `{{ value | label }}` Jinja filter or `STATUS_LABELS.get(value, value)` in handlers. All templates use this single source of truth.

### Scope
- All `<select>` option labels
- All status badge text
- All backend enum display values
- Analytics "no_plan" → "Нет данных"
- Emergency dropdowns
- Readiness "unknown No heartbeat received" → "Не определено · нет heartbeat"

### Quick win
This step alone eliminates ~40% of the English-in-Russian-UI problem across all pages.

---

## Strategy: UUID / Business Codes (UI.2.2)

### Problem
Full 36-char UUIDs displayed as primary labels in analytics, bookings, PoP, and devices.

### Approach
Create a **short_display helper** in `apps/portal-web/display.py`:

```python
def short_display(value: str, prefix: str = "", fallback: str = "—") -> str:
    """Return short business code or truncated UUID."""
    if not value:
        return fallback
    # If it's a UUID, show first 8 chars
    if len(value) == 36 and value.count("-") == 4:
        return f"{prefix}{value[:8]}…" if prefix else f"…{value[-8:]}"
    return value
```

Use in templates: `{{ campaign_id | short_code("C-") }}` → `C-b844a2fe…`

### Hierarchy of identifiers
1. **Business code** (e.g., `C-63939f`) — primary display
2. **Short UUID** (e.g., `…b844a2fe`) — secondary, muted, small font
3. **Full UUID** — hidden behind "Подробнее" toggle or title attribute only

### Scope
- Campaign list: use business code or `C-{8chars}…`
- Analytics: replace UUID column with `{name} ({short_code})`
- Bookings: replace `865d6...` with proper short refs
- PoP: suppress `media/current/slot-000` internal paths
- Readiness: use device codes instead of UUIDs
- All detail page links: use short codes in URL path where available

### Note
UI.C1.R1 already uses UUID in URLs as a fallback. This is a temporary solution. UI.2.2 will prefer business codes when available.

---

## Strategy: Tables / Pagination (UI.2.3)

### Problem
Admin (83 users) and Readiness (63 devices) render as single enormous tables. No pagination, search, or density control.

### Approach

**Pagination component** — Jinja macro reusable across all templates:

```
[← Назад] 1 2 3 … 9 [Далее →]  (20 на странице)
```

**Table enhancements:**
- `table-striped` class — alternate row backgrounds
- `table-hover` class — row highlight on hover
- `table-compact` class — smaller padding for dense data
- `col-actions` class — right-aligned action column, min-width

**Search/filter:**
- Admin users: search by name/login
- Readiness: filter by status dropdown (already exists)

### Scope
- Admin: 20 users/page + search
- Readiness: 20 devices/page (status filter exists)
- All tables: hover highlight + compact density option

---

## Strategy: Page Headers / Layout (UI.2.4)

### Problem
- 10+ pages use generic `<div>` instead of `<h1>`
- Inconsistent subtitle/primary action placement
- C4: Admin sidebar shows only 2 links (separate base template)

### Approach

**Standard page header block** — Jinja macro or include:

```
<h1 class="page-title">{{ title }}</h1>
<p class="page-subtitle">{{ subtitle }}</p>
<div class="page-actions">
  <a class="btn btn-primary">{{ primary_action }}</a>
</div>
```

**Template audit:**
- Apply to all 17 page templates
- Fix admin.html to extend the same base layout as other pages (fixes C4)

### Scope
- Every page gets `<h1 class="page-title">`
- Every page gets a subtitle (one line, business context)
- Primary action visible in page header (not buried in content)
- Admin sidebar fixed to show full navigation

---

## Strategy: Empty States (UI.2.5)

### Problem
Planning, Deployment, and Help have empty/broken content. Users see blank pages or technical forms.

### Approach

**Empty state component:**

```
<div class="empty-state">
  <div class="empty-state-icon">📋</div>
  <h3>Нет данных за период</h3>
  <p>Выберите даты и нажмите «Показать», чтобы увидеть план рекламного времени.</p>
</div>
```

### Scope
- Planning: replace ID form with real filters + empty state
- Deployment: fill or hide empty paragraphs, show "Развёртывание не выполнялось"
- Help: fill empty paragraphs with real content

---

## Strategy: Action Design (UI.2.6)

### Problem
Campaign table cells have 3 stacked `<form>` elements. Actions inconsistent across pages.

### Approach

**Action bar pattern:**

```
<div class="action-group">
  <a class="btn btn-sm btn-ghost">Открыть</a>
  <button class="btn btn-sm">📦 Подготовить</button>
  <button class="btn btn-sm btn-muted">Архив</button>
</div>
```

Consolidate into a single inline flex container. Destructive actions (archive, cancel) use muted styling and are visually separated.

### Scope
- Campaign table: merge 3 forms into action-group
- All tables: consistent action column width and alignment

---

## Strategy: Responsive (UI.2.8)

### Problem
Sidebar 220px fixed, tables overflow on narrow screens, no mobile support.

### Approach

**Desktop-first (≥1366px is target):**
- Sidebar: 220px fixed at ≥1366px; collapsed toggle icon at 1024–1365px
- Tables: `overflow-x: auto` wrapper with min-width hint
- Metric grids: `auto-fill, minmax(180px, 1fr)` — already adaptive
- Forms: flex-wrap for tight layouts

**Not doing:** mobile (768px) full support. Not a mobile product.

---

## UI.2 Split

| Step | Name | Scope | Tests |
|---|---|---|---|
| UI.2.0 | **Design Gate** ✅ | This document | — |
| UI.2.1 | Language & Status Localization | labels.py + all templates | ≥15 tests |
| UI.2.2 | Business Codes / UUID Cleanup | display.py + all templates | ≥20 tests |
| UI.2.3 | Tables / Pagination / Search | table macros, admin, readiness | ≥20 tests |
| UI.2.4 | Page Headers / H1 / Layout | all templates, fix C4 | ≥20 tests |
| UI.2.5 | Empty States / Help / Deployment | planning, deployment, help | ≥15 tests |
| UI.2.6 | Business Workflow Polish | campaigns, creatives, publications | ≥25 tests |
| UI.2.7 | Operational Pages Polish | analytics, PoP, devices, readiness | ≥20 tests |
| UI.2.8 | Responsive / Visual Polish | CSS, grids, icons, footer | ≥15 tests |
| UI.2.9 | Visual Regression Gate | full browser audit + regression | ≥30 tests |
| UI.2.10 | Closure / Business Demo Gate | docs, final audit | — |

### Rationale for the order

1. **UI.2.1 first** — localization is the highest-impact, lowest-risk quick win. A single Python dict + Jinja filter changes English→Russian across all pages. Zero structural changes.

2. **UI.2.2 next** — UUID cleanup depends on localization (label display). Short codes in links depend on C1 fix being stable.

3. **UI.2.3–2.5** — structural but isolated changes (tables, headers, empties). Don't depend on each other.

4. **UI.2.6–2.7** — polish phases depend on 2.1–2.5 being done.

5. **UI.2.8** — visual polish and responsive last, to avoid re-polishing after structural changes.

### Quick Wins vs Systemic

**Quick wins (immediate):**
- UI.2.1: localization dict + filter (1 file + template updates)
- UI.2.2: short_display helper (1 file + template updates)
- UI.2.4: H1/page-header macro (1 macro + templates)
- UI.2.5: empty state component (1 component + 3 pages)

**Systemic (require planning):**
- UI.2.3: pagination search (component + 2–3 pages)
- UI.2.8: responsive sidebar (CSS restructuring)

---

## Test Strategy

| Step | Test File | Min Tests | Focus |
|---|---|---|---|
| UI.2.1 | `test_ui21_language_localization.py` | 15 | Label map completeness, all statuses RU, no EN in dropdowns |
| UI.2.2 | `test_ui22_business_codes.py` | 20 | No full UUID as primary label, short codes everywhere |
| UI.2.3 | `test_ui23_tables_pagination.py` | 20 | Pagination present, search works, row limits |
| UI.2.4 | `test_ui24_page_headers.py` | 20 | H1 on every page, subtitle present, C4 fixed |
| UI.2.5 | `test_ui25_empty_states.py` | 15 | No blank pages, empty states render |
| UI.2.6 | `test_ui26_business_workflow.py` | 25 | Actions consolidated, no 3-form cells |
| UI.2.7 | `test_ui27_operational_pages.py` | 20 | No synthetic labels, no raw paths |
| UI.2.8 | `test_ui28_responsive_polish.py` | 15 | CSS valid, grids unified, icons consistent |
| UI.2.9 | `test_ui29_visual_regression.py` | 30 | Full template audit, security, regression |

**Continuous:** All UI.1 targeted suites (424 tests) run after each step. Full portal regression (1802 tests) run at UI.2.9.

**Honesty:** 8 pre-existing live integration errors are never hidden.

---

## Security / Source Boundaries

UI.2 must preserve all existing security properties:
- RBAC guards and sidebar permission filtering
- No secrets in templates
- No traceback exposure
- No raw JSON as main UI
- No `|safe` on user-supplied data
- No script tags
- No localStorage
- No CDN
- Emergency dry-run banner preserved
- Deployment NO-GO warning preserved
- Feature flag defaults unchanged
- Production switch NO-GO preserved

---

## Risks

| Risk | Mitigation |
|---|---|
| Localization breaks status-based logic | Use labels only for display; backend values unchanged |
| UUID→short_code breaks links | UUID fallback tested by UI.C1.R1, preserve in href |
| Pagination breaks existing tests | Update test expectations, add pagination-specific tests |
| Admin sidebar fix breaks other admin pages | Test all admin sub-pages after fix |
| Responsive sidebar breaks tablet users | 1366px minimum; collapse at 1024px, not remove |

---

## GO/NO-GO for UI.2.1

### GO Criteria

- ✅ UI.2 scope documented (this document)
- ✅ All UI.VA.3 issues mapped to UI.2 steps
- ✅ C1 confirmed fixed (UI.C1.R1, 32 tests passed)
- ✅ C4 confirmed still present (admin sidebar 2 links, to be fixed in UI.2.4)
- ✅ UI.2 split approved (10 steps)
- ✅ Source boundaries documented
- ✅ No code changes in UI.2.0 (docs-only)
- ✅ Design tokens assessment: adequate, extend not replace

### Decision: **GO for UI.2.1**

UI.2.1 is the safest, highest-impact first step:
- One new file (`labels.py`)
- Template updates (Jinja filter)
- No structural changes
- No CSS changes
- No backend/API/route changes
- Eliminates ~40% of English-in-Russian-UI issues

---

## Documents Created

- `docs/architecture/ui2-modern-product-ui-redesign-design-gate.md` — this file
- `docs/product/current-project-state-after-ui20.md` — state update
