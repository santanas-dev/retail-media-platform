# B.3.4 — Portal Read-Only Placement Visibility

**Date:** 2026-06-29  
**Predecessor:** B.3.3.1 Regression Delta + Real API Validation (`de763c7`)  
**Subject:** Portal read-only visibility for placements — campaign detail block + placement detail page.

---

## What was added

### 1. Campaign detail — placements block
`campaigns_detail.html` — new section "Размещения" with table:
- placement_code (link to detail), name, status, priority, date range
- Empty state: "Размещения пока не созданы"
- Backend-driven: `GET /api/campaigns/{id}/placements`

### 2. Placement detail page
`/placements/{placement_id}` — new route + template `placement_detail.html`:
- Read-only: placement_code, name, status, priority, dates, timestamps
- Targets section: store/surface/carrier with Russian labels
- Empty targets: "Цели не заданы"
- 404/403 handling (cross-advertiser isolation via backend)

### 3. BackendClient additions
- `list_campaign_placements(access_token, campaign_id)` → `GET /api/campaigns/{id}/placements`
- `get_placement(access_token, placement_id)` → `GET /api/placements/{id}`
- `get_placement_targets(access_token, placement_id)` → `GET /api/placements/{id}/targets`

### 4. Template restructuring
- Old "Placement / Schedule Block" → split into:
  - "Размещения" (new, backend-driven)
  - "Расписания" (renamed from "Размещения", preserves schedule CRUD)

---

## What was NOT added (intentionally)

- ❌ No create/update/delete placement in portal
- ❌ No CRUD forms in placement_detail.html
- ❌ No JS/CDN/localStorage
- ❌ No raw UUIDs in visible template text
- ❌ No audit/action buttons on placement detail

---

## Tests: 21/21

| Group | Tests |
|---|---|
| Campaign detail placements block | 6 |
| Placement detail page | 8 |
| Security (no JS/CDN/localStorage) | 4 |
| Not-found handling | 2 |
| **Total** | **21** |

---

## Portal Regression

| Metric | Value |
|---|---|
| Passed | **863** |
| Failed | **0** |
| Skipped | 32 |
| Errors | 8 (pre-existing, `test_portal_backend_live_integration`) |

---

## Preserved (unchanged)

- ✅ Backend placement API
- ✅ Campaign submit validation
- ✅ Publication flow
- ✅ generated_manifests FK
- ✅ campaign_targets, kso_placements
- ✅ RBAC/RLS — portal uses `campaigns.read` permission
- ✅ Cross-advertiser isolation — backend returns 403, portal shows forbidden

---

## GO/NO-GO

**GO for B.3.5 Closure & B.4 handoff.**
