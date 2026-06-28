# Business Logic Audit — Retail Media Platform Portal

**Date:** 2026-06-26
**Scope:** Portal (`apps/portal-web/`) + Backend (`backend/app/domains/`)
**Methodology:** 9-tool business logic validation
**Sources:** `main.py` (3577 lines), `rbac.py`, `campaigns/service.py`, `approvals/service.py`, `publications/service.py`, `manifests/service.py`, `scheduling/service.py`, `backend_client.py`, 19 templates
**Test status:** Portal 756 ✅ + 20 skipped, Backend 807 ✅ (venv) = 1563+ total

---

## Executive Summary

| Finding | Severity | Count | Detail |
|---------|----------|-------|--------|
| 🔴 Status mismatch: "in_review" ≠ "pending_approval" | P0 | 1 | Campaign KPI always 0 |
| 🟠 Uncounted statuses | P1 | 3 | Schedule "active", Manifest "draft", Batch "pending_approval" |
| 🟡 Legacy test-kso methods | P1 | 6 | In BackendClient, unused by portal |
| 🟡 Backend service tests missing | P2 | All domains | Services lack direct unit tests |
| 🟢 Business rules enforced | ✅ | 11 | In service layer |
| 🟢 RBAC on all routes | ✅ | 16 entries + 33 guards |
| 🟢 Maker-checker enforced | ✅ | approval_service.py:370 |
| 🟢 RLS scope enforcement | ✅ | 42 endpoint tests |
| 🟢 No secrets in HTML | ✅ | Verified in all templates |
| 🟢 Tests passing | ✅ | Portal 756 + Backend 807 |

---

## Tool 1-8: Compiled Findings

### Decision Table (Tool 1)
Backend enforces: EDITABLE_STATUSES = {draft, rejected}, SUBMIT_FROM_STATUSES = {draft, rejected}
Approve requires "in_review", reject requires "in_review". Approved/archived are immutable.

### State Transitions (Tool 2)
Actual backend state machine: draft → in_review → approved / rejected. Rejected → in_review (re-submit).
Draft → archived. No other valid transitions.

🔴 P0: Campaign status after submit is "in_review" (backend), but portal Dashboard KPI and campaign list count "pending_approval". Result: submitted campaigns invisible in UI.

### Business Rules (Tool 3)
11 rules found in backend service layer:
BR-001: Only draft/rejected editable (`_check_editable`)
BR-002: Submit from draft/rejected only
BR-003: Submit requires channels + targets + valid renditions
BR-004: Submit → "in_review"
BR-005: Approve requires "in_review"
BR-006: Reject requires "in_review"
BR-007: Approve records approved_by + approved_at
BR-008: Creative must be "approved" for campaign submit
BR-009: Rendition must be "valid"
BR-010: Maker-checker enforced
BR-011: created_by recorded

### Traceability (Tool 4)
23/23 portal routes have tests. 16 routes in PAGE_PERMISSION_MAP.

### Process Walkthrough (Tool 5)
8-step campaign lifecycle mapped. Critical gap: portal cannot add channels/targets/renditions — campaigns created from portal may fail `_check_campaign_ready()` at submit.

### Edge Cases (Tool 6)
22 edge cases cataloged. Most untested at boundaries.

### Role Matrix (Tool 7)
6 roles × 24 actions mapped. RBAC enforced via PAGE_PERMISSION_MAP.

### Data Flow (Tool 8)
Full pipeline traced: creative → campaign → schedule → manifest → report.

---

## Tool 9: Status String Audit (FULL RESULTS)

### Campaign Statuses

| Backend writes (service.py) | Portal counts (main.py) | Match? |
|---|---|---|
| `"draft"` (line 268) | `"draft"` (line 166) | ✅ |
| `"in_review"` (line 309) | `"pending_approval"` (line 167) | 🔴 MISMATCH |
| `"approved"` (line 327) | `"approved"` (line 168) | ✅ |
| `"rejected"` (line 347) | `"rejected"` (line 169) | ✅ |
| `"archived"` (line 798) | `"archived"` (line 170) | ✅ |
| `"active"` (line 589,613,639) | `"active"` (line 165) | ✅ |

**Root cause:** `campaigns/service.py:309` sets `campaign.status = "in_review"` after submit.
`main.py:167` counts `c.get("status") == "pending_approval"`.
Portal correctly uses `"in_review"` in ONE place: `main.py:199` (approvals pending count).

### Publication Batch Statuses

| Backend writes | Portal counts | Match? |
|---|---|---|
| `"draft"` | `"draft"` | ✅ |
| `"manifest_generated"` | → counted as "published" (line 190) | ✅ (deliberate) |
| `"published"` | `"published"` | ✅ |
| `"approved"` | `"approved"` | ✅ |
| `"pending_approval"` (on object via approvals) | `"pending_approval"` (line 194) | ⚠️ may not match batch lifecycle |

### Schedule Statuses

| Backend writes | Portal counts | Match? |
|---|---|---|
| `"draft"` | `"draft"` | ✅ |
| `"archived"` | — | ⚠️ not counted |
| — | `"active"` (line 185) | ⚠️ never written by schedule service |

### Manifest Statuses

| Backend writes | Portal counts | Match? |
|---|---|---|
| `"generated"` | → "published" bucket (line 190) | ✅ |
| `"published"` | → "published" bucket | ✅ |
| — | `"draft"` (line 189) | ⚠️ never written by manifest service |

---

## Verification: Actual Test Results

```
Portal:  756 passed, 20 skipped, 1 error (pytest import in live integration test)
Backend: 807 passed (venv+pytest), 26 warnings
Total:   1563+ passing
```

The 1563 tests confirm functional correctness but do NOT catch the status string mismatch because tests use mock data where status values are set by the test, not by the actual backend service.

---

## Recommendations

### P0 — Fix Immediately
1. Fix "in_review" vs "pending_approval" mismatch:
   - Quick fix: add status mapping in portal handler or BackendClient response transform
   - Long-term: rename "in_review" → "pending_approval" in backend + migration
   - Lines to fix: main.py:167, main.py:1502 (and any other "pending_approval" references)

### P1 — Fix This Week
2. Audit and fix schedule "active" counting (main.py:185 has no backend source)
3. Audit and fix manifest "draft" counting (main.py:189 has no backend source)
4. Remove or mark deprecated the 6 legacy test-kso methods in BackendClient

### P2 — Backlog
5. Add backend service unit tests (mutation testing would reveal gaps)
6. Add portal UI for channels/targets/renditions management
7. Add boundary edge case tests (256-char names, 51MB files, etc.)
