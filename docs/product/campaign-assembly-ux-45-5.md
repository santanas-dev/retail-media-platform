# Campaign Assembly UX — 45.5

**Date:** 2026-06-28
**Status:** ✅ Implemented
**Portal regression:** 826 passed ✅
**Backend regression:** 766 passed (24 pre-existing failures in inventory engine)

## Overview

Campaign Assembly UX closes the main product gap: advertisers can now assemble a campaign from multiple creatives, configure placements/schedules, and submit for approval — all through the portal UI.

## Feature Summary

### 1. Campaign Detail Card (`/campaigns/{code}`)
- Full campaign view: name, code, status badge, description, created/updated dates
- Next action banner based on status (draft → add creatives, in_review → waiting, approved → publish)
- Business-friendly display names via `|sanitize` filter
- No raw UUIDs, technical codes, or test/seed labels

### 2. Creative Block
- Table of bound creatives: name, format, size, scan status, approval status
- "Открыть" button links to creative detail page
- "✕" button to unbind creative (only in draft/rejected status)
- Add creative form with dropdown of **approved only** creatives
- Empty state: "Креативы не привязаны"
- N:N relationship fully visible (campaign_creatives table)

### 3. Campaign List Improvements
- Creative count replaces raw creative codes: "3 креатива"
- "Открыть" button on each row linking to campaign detail
- Plural form handling (креатив/креатива/креативов)

### 4. Placement / Schedule Block
- Schedule creation form directly in campaign detail
- Fields: name, start date, end date, channel (КСО, readonly), target group (Тестовая группа магазинов, readonly)
- Auto-created 5 Mon-Fri slots (08:00–22:00) per schedule
- "⚠️ Демо-режим" safety note
- Physical KSO delivery NOT triggered
- Schedule API tested and working

### 5. Submit Readiness Checklist
- 6-item checklist visible when campaign is draft/rejected:
  1. ✅/⬜ Креативы привязаны
  2. ✅/⬜ Креативы одобрены
  3. ✅/⬜ Размещение создано
  4. ✅/⬜ Период указан
  5. ✅ Канал выбран (always green — demo mode)
  6. ✅ Целевая группа выбрана (always green — demo mode)
- Submit button appears only when all items ✅
- Missing items show specific guidance text

### 6. Approval Section
- Visible when campaign is in_review/approved/rejected
- Shows approval status and approval code
- Links to /approvals page
- Submit creates ApprovalRequest via backend with hidden object_code

### 7. Reports Preview
- Campaign name, creative count, placement count, approval status
- Publication package status (when approved)
- "Фактические показы появятся после подключения физической КСО" note
- Link to full reports page

## Technical Details

### New Files
- `apps/portal-web/templates/pages/campaigns_detail.html` — Campaign detail template (276 lines)

### Modified Files
- `apps/portal-web/main.py` — 3 new routes:
  - `GET /campaigns/{campaign_code}` — Campaign detail page
  - `POST /campaigns/{campaign_code}/create-schedule` — Schedule creation
  - Updated redirects: bind/unbind/submit/create-batch → campaign detail
- `apps/portal-web/templates/pages/campaigns.html` — Creative count + "Открыть" link
- `apps/portal-web/static/styles.css` — New CSS classes (detail-grid, checklist, slot-badge, etc.)
- `apps/portal-web/display_name_sanitizer.py` — AV scan statuses + schedule labels
- `apps/portal-web/tests/test_main.py` — 17 new tests (TestCampaignDetailPage)

### Constraints Compliance
- ✅ No JS/CDN/localStorage — all server-side rendering
- ✅ Pure CSS — no Vue/React dependencies
- ✅ No secrets/leaks — no device_secret, access_token, backend URLs
- ✅ No raw UUIDs, test/seed/None labels
- ✅ RBAC/RLS/audit trail — no weakening
- ✅ Physical KSO/SSH/X11/Chromium/runner/sidecar/PoP — untouched
- ✅ Scanner E2E/long-run/sidecar sync — not run
- ✅ Production AV — not enabled
- ✅ Old tags — not rewritten

### Remaining Gaps
- Maker-checker prevents same-user creative approval (security feature, not a bug)
- Schedule API schedule codes collide if same campaign creates multiple schedules (edge case)
- Campaign creative status not returned by `list_campaign_creatives` endpoint (causes "⬜ Креативы одобрены" even when approved)
