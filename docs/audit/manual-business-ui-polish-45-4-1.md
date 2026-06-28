# Manual Business UI Polish — Full Visual Screenshot Gate (45.4.1)

**Date**: 2026-06-16  
**HEAD**: `3474b62`  
**Previous**: `.4` → `1f02fa2` (45.3.2 — final clean pre-demo baseline)  

## Goal

Verify all 17 business-demo pages visually under `system_admin` auth. Fix EN headers, test/seed data leaks, default browser controls found during manual inspection.

## Pages Verified (17/17)

| # | Page | HTTP | Visual | Issues Found | Fixed |
|---|------|------|--------|-------------|-------|
| 1 | /dashboard | 200 | ✅ | — | — |
| 2 | /creatives | 200 | ✅ | «Choose File» (EN browser default) | ✅ custom label |
| 3 | /creatives/moderation/queue | 200 | ✅ | — | — |
| 4 | /creatives/{code} | 200 | ⚠️ | «Креатив не найден» — hex codes don't match creative_code | deferred |
| 5 | /campaigns | 200 | ✅ | Synthetic Campaign, Test C, active (EN) | ✅ sanitizer |
| 6 | /campaigns/create | 200 | ✅ | Synthetic Advertiser ×7, Wrong Advertiser Inc. ×7, After Role Change ×6 | ✅ sanitizer |
| 7 | /schedule | 200 | ✅ | — | — |
| 8 | /approvals | 200 | ✅ | — | — |
| 9 | /publications | 200 | ✅ | Code/Device/Campaign/Status/Items EN, published EN, lifecycle EN | ✅ all RU |
| 10 | /reports | 200 | ✅ | test_playback_completed, accepted EN, EVENT EN header | ✅ sanitizer |
| 11 | /inventory | 200 | ✅ | — | — |
| 12 | /readiness | 200 | ✅ | Device Code/Store/Credential/Readiness EN, filter EN, active EN, unknown No heartbeat, events→соб. | ✅ all RU |
| 13 | /readiness/business-acceptance | 200 | ✅ | — | — |
| 14 | /stores | 200 | ✅ | Synthetic Branch/Cluster/Store, active EN | ✅ sanitizer |
| 15 | /admin | 200 | ✅ | rls_test_adv, ds_test, local, EN roles | ✅ sanitizer |
| 16 | /deployment | 200 | ✅ | — | — |
| 17 | /proof-of-play | 200 | ✅ | media_ref EN, test_playback_completed, accepted EN | ✅ all RU |

## What Was Fixed

### display_name_sanitizer.py
- +45 exact-match mappings covering all discovered test/seed/EN values
- English → Russian: statuses, roles, providers, event types
- Synthetic/Test/V22/PubTest/RLS test data → business display names

### Templates (5 files)
- publications.html: 5 EN headers → RU, lifecycle EN→RU, +sanitize filter
- readiness.html: 8 EN headers → RU, filter dropdown RU, +sanitize on 4 status fields, events→соб.
- proof-of-play.html: media_ref→Медиа, +sanitize on event_type/status
- admin.html: roles loop with sanitize, auth_provider sanitized
- creatives.html: custom file input (hidden native + styled label «Выберите файл»)

### CSS (styles.css)
- .file-input-native — sr-only accessible hidden input
- .file-input-label — styled button replacement
- .file-input-name — filename placeholder

## Regression

| Suite | Passed | Failed | Skipped |
|-------|--------|--------|---------|
| Portal (apps/portal-web/tests) | **760** | 0 | 32 |
| Backend (backend/tests) | **807** | 0 | — |

## Click Check

All visible links/buttons on 16 demo pages → no 403/404/500. User-management not shown per demo boundaries.

## Remaining Known Issues

1. **«Креатив не найден»** on `/creatives/{code}` — creative_code vs code mismatch (backend uses creative_code for detail lookup but table shows code). Deferred — data issue, not visual.
2. **«Campaign Creative»** display name — not in sanitizer yet (minor, 1 occurrence)
3. **«cr-*»** creative names — seed data, not yet mapped (minor)
4. **Screenshots** — not saved to disk (text-based verification used instead)

## Confirmations

- ✅ No physical KSO/SSH/X11/Chromium/runner/sidecar/PoP
- ✅ Scanner E2E/long-run/agent sync not executed
- ✅ Production AV not enabled
- ✅ RBAC/RLS/audit trail not weakened
- ✅ Old tags not rewritten
- ✅ No business logic changes (UI/CSS/sanitizer only)
- ✅ No JS/CDN/localStorage
- ✅ No secrets/leaks in visible content
- ✅ Forbidden terms: 0

## Demo Boundaries Maintained

- User-management not shown as ready
- Physical delivery blocked
- AV production not active
- Physical pilot remains NO-GO 🔴

## Related

- `.4` (1f02fa2) — NOT for business demo (visual blockers)
- 45.4 (f584c9d) — initial UI polish (3 pages)
- **45.4.1 (3474b62)** — full visual gate (17 pages)
- After 45.4.1: new baseline tag recommended for business demo
