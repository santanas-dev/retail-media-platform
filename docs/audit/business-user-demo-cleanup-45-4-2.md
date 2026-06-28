# Business User Demo Cleanup — 45.4.2

**Date:** 2026-06-16  
**Branch:** main  
**Scope:** UI-only cleanup for business demo — templates, display mapping, server-side limit, wording, navigation visibility

## P0 — Critical blockers (all closed)

| # | Issue | Fix |
|---|-------|-----|
| 1 | `/campaigns` — inline-edit rows (2 строки на кампанию) | Single-row table, compact edit form in same row, no inline-actions-row |
| 2 | `/dashboard` — большой технический баннер «🔴 Запуск заблокирован» | → «ℹ️ Физический запуск требует отдельного подтверждения» |
| 3 | `/reports` — test_playback_completed/d4-synth события | Added `_is_test_pop_event()` filter in main.py + sanitizer business labels |

## P1 — High priority (all closed)

| # | Issue | Fix |
|---|-------|-----|
| 4 | `/dashboard` — «⚠️ Часть данных недоступна» | Removed alarming message |
| 5 | `/dashboard` — "Dashboard" | → «Главный экран» |
| 6 | `/campaigns` — status "active" EN | → «Активна» badge + CSS class `status-badge-active` |
| 7 | `/campaigns` — 20× «⚠️ Нет креативов» | → «Креатив не выбран» calm text |
| 8 | `/publications` — 74 элемента без пагинации | Limit 20, sorted desc by created_at, badge «N из M» |
| 9 | `/reports` — EN labels (EVENT, draft, published) | → «Событие», status через `\|sanitize` |
| 10 | Навигация — 15 пунктов, технические разделы | → «Основное»/«Аналитика»/«Администрирование», КСО-разделы сгруппированы |

## P2 — Quick fixes (all closed)

| # | Issue | Fix |
|---|-------|-----|
| 11 | Duplicate action-bar/breadcrumbs | Removed duplicate links from campaigns & publications |
| 13 | `/publications` — EN workflow note | → «Процесс: Черновик → Согласование → ...» |
| 14 | `/reports` — "NO-GO" | → «не запущен» |
| 15 | `/admin` — "MFA" | → «2FA» |
| 16 | `/reports` — placeholders (camp_code, cr_code) | → «Кампания», «Креатив», «КСО» |

## P3 — Deferred to roadmap

| # | Issue | Status |
|---|-------|--------|
| 17 | «Рекламное время» empty state | Backlog |
| 18 | CSV-ссылки не в стиле кнопок | Backlog |
| 19 | Breadcrumb hierarchy | Backlog |
| 20 | Security_admin sanitizer | Already in sanitizer (line 85) |

## Creative detail fix

- Added `/creatives/{code}` link from creatives list (clickable business-chip)
- Route `/creatives/{code}` returns 200 for valid codes

## Files changed

- `apps/portal-web/templates/pages/campaigns.html` — single-row, no inline-edit rows, RU statuses
- `apps/portal-web/templates/pages/dashboard.html` — business banner, RU title, no technical gates
- `apps/portal-web/templates/pages/reports.html` — RU labels, business placeholders, sanitized statuses
- `apps/portal-web/templates/pages/publications.html` — pagination, workflow RU, no duplicate action-bar
- `apps/portal-web/templates/pages/creatives.html` — clickable creative codes
- `apps/portal-web/templates/pages/admin.html` — MFA→2FA
- `apps/portal-web/templates/base.html` — navigation restructured
- `apps/portal-web/main.py` — test event filter, publications limit, pilot_nogo text
- `apps/portal-web/tests/test_main.py` — +17 guard tests, updated 12 pre-existing tests
- `backend/tests/test_e2e_real_business_flow_4361.py` — updated for business banner
- `backend/tests/test_reports_portal_42_3.py` — updated for RU labels

## Regression

- Portal: **756 passed**, 20 skipped, 0 failed
- Backend: **807 passed**, 0 failed (5 pre-existing fixed)
- No JS/CDN/localStorage
- No secrets/leaks
- RBAC/RLS/audit trail not weakened
- No business logic changes
- No physical KSO/SSH/X11/Chromium/runner/sidecar/PoP
- Scanner E2E/long-run/agent sync not executed
- Production AV not enabled
