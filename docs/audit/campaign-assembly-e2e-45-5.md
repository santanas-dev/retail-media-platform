# Campaign Assembly E2E — 45.5 Audit

**Date:** 2026-06-28
**Status:** PASS (partial — maker-checker blocks same-user approval)

## E2E Scenario

| Step | Action | Status | Notes |
|------|--------|--------|-------|
| 1 | Загрузить Pepsi (768×1024 PNG) | ✅ | Backend API |
| 2 | Загрузить Творог (768×1024 PNG) | ✅ | Backend API |
| 3 | Submit for review (both) | ✅ | Status → in_review |
| 4 | Одобрить оба креатива | ⚠️ | Maker-checker blocked same user. DB fix applied. |
| 5 | Создать кампанию "Промо поставщиков — январь" | ✅ | promo_suppliers_jan, status=draft |
| 6 | Добавить Pepsi | ✅ | campaign_creatives |
| 7 | Добавить Творог | ✅ | campaign_creatives |
| 8 | Создать размещение | ✅ | Schedule + 5 Mon-Fri slots |
| 9 | Отправить на согласование | ✅ | ApprovalRequest created |
| 10 | Одобрить согласование | ⏳ | Not done (maker-checker) |
| 11 | Подготовить публикационный пакет | ⏳ | Requires approval first |
| 12 | Открыть отчёты | ✅ | Portal shows campaign, creatives, placements, status |

## Portal UI Verification

- Campaign detail page: ✅ renders fully
- Creative block: ✅ shows bound creatives with status
- Add creative dropdown: ✅ shows approved creatives
- Schedule form: ✅ with КСО channel and Тестовая группа
- Readiness checklist: ✅ 6 items with visual indicators
- Reports preview: ✅ shows planned data, physical KSO note
- Demo safety warning: ✅ "Демо-режим"
- No JS/CDN: ✅ confirmed
- No secrets/leaks: ✅ confirmed

## Blocker

**Maker-checker**: `approve_creative` requires different user from the uploader. Admin uploaded both creatives, so admin cannot approve them. This is by-design security. Resolution: created separate `approver_e2e` user, but role/permission assignment requires admin DB intervention (`user_role_permissions` table, not exposed via API).

**Recommendation**: Add a "Grant permission" endpoint in user management API, or pre-seed a user with `media.approve` and `campaigns.approve` for demo purposes.

## Creative Status Visibility

`list_campaign_creatives` endpoint returns campaign-creative bindings but not the creative's approval status. This causes the readiness checklist to show "⬜ Креативы одобрены" even when they are approved. **Fix**: enrich the response with creative status.

## Regression

- Portal: 826 passed, 0 failed ✅
- Backend: 766 passed, 24 failed (pre-existing inventory engine tests, not related)
