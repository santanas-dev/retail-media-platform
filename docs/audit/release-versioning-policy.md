# Release Versioning Policy

> **Принцип:** Каждый minor release tag фиксирует стабильную baseline с green regression.
> Patch tags (hotfix) фиксируют критические исправления поверх существующего minor без добавления нового функционала.

## Tag Naming Convention

```
v<MAJOR>.<MINOR>.<PATCH>-<descriptor>
```

- **MAJOR**: архитектурные изменения (пока 0 — pre-production)
- **MINOR**: milestone с новым функционалом
- **PATCH**: hotfix поверх существующего minor
- **descriptor**: короткое описание milestone/fix

## Requirements for Every Tag

1. Green full regression (все 6 suites)
2. Clean git status
3. No secrets in docs/output/commits
4. No test-kso as primary path
5. RBAC/RLS enforced, not weakened

## Release History

### v0.12.0-product-workflow-backend-manifest (2026-06-16)

**Type:** Minor release.

**Includes:**
- 41.0.0 — Portal UI Hygiene Baseline (CSS-only, no redesign)
- 41.1 — Creative Upload UX (multipart form, server-side POST)
- 41.1.1 — Remove JS confirm (pure POST forms, no inline scripts)
- 41.2 — Business Campaign Creation UX (orchestrated campaign + placement + schedule + slots)
- 41.2.1 — Campaign Submit Approval Integration (Production ApprovalRequest flow, completeness guards)
- 41.3 — Approval Decision UX (campaign summary, per-row approve/reject, maker-checker)
- 41.3.1 — CampaignCreative is_active Compatibility Guard (safe helper, no ORM column)
- 41.4 — Approved Campaign to Publication Batch (code-based endpoint, backend-only warning)
- 41.4.1 — Full Publication Batch Workflow & Manifest Generation
  - ScheduleRun ORM model (table existed, ORM was missing)
  - Batch lifecycle: draft → pending_approval → approved → manifest_generated → published
  - Manifest version N+1 generation (full playlist, campaign material included)
  - Previous manifest preserved (old draft versions → cancelled on regenerate)
  - Backend publish status only — **no physical KSO delivery**

**Regression:** 5260 passed, 32 skipped, 0 failed (5292 total, 0 failed).

**Pilot Status:** NO-GO 🔴
- HW scanner E2E: not executed (no hardware)
- Controlled long-run: not executed
- Physical KSO delivery gate: not approved
- Gates B, C, D: documented, not executed

**Remaining Blockers:**
- HW scanner E2E validation (barcode → campaign match)
- Controlled long-run (1h/8h/48h options, monitoring)
- Explicit physical KSO approval gate

**Non-Blocking Technical Debt:**
- `ScheduleRun` raw SQL in `create_batch_from_campaign` (ORM exists, can migrate later)
- `CampaignCreative.is_active` ORM/schema mismatch (deferred to migration track)
- 7 legacy BackendClient methods (dead code, unused by portal)
- `/deployment` page: demo-only (documentation, no backend data)

---

### v0.12.1-pilot-runbook-go-no-go-baseline (2026-06-16)

**Type:** Patch release on v0.12.0.

**Includes:**
- v0.12.0-product-workflow-backend-manifest (full baseline)
- 41.5 — Pilot Runbook & GO/NO-GO Pack
  - `docs/pilot/one-kso-pilot-runbook.md` — full pilot runbook (scope, roles, prerequisites, phases, stop criteria, rollback, evidence, communications)
  - `docs/pilot/go-no-go-checklist.md` — GO/NO-GO decision matrix (9 categories, 50+ criteria)
  - `docs/pilot/physical-approval-tokens.md` — 7 approval tokens (scanner → long-run → KSO access → delivery → sidecar → PoP → autostart)
  - `docs/pilot/evidence-checklist.md` — 21 backend evidence items (captured) + 12 physical items (pending)
  - `docs/pilot/known-risks-and-deferred-items.md` — 3 blockers, 5 non-blocking tech-debt, 5 accepted risks, 7 deferred items
  - Updated `docs/audit/technical-debt-next-actions.md`
  - Updated `docs/audit/product-backend-frontend-gap-analysis.md`

**Regression:** 5260 passed, 32 skipped, 0 failed (inherited from v0.12.0 — docs-only, no code changes).

**Pilot Status:** NO-GO 🔴
- HW scanner E2E: not executed (no hardware)
- Controlled long-run: not executed
- Physical KSO delivery gate: not approved
- All 7 approval tokens: PENDING ⛔

**Remaining Blockers:**
- HW scanner E2E validation (barcode → campaign match)
- Controlled long-run (1h/8h/48h options, monitoring)
- Explicit physical KSO approval gate

**Non-Blocking Technical Debt:**
- `ScheduleRun` raw SQL in `create_batch_from_campaign` (ORM exists, can migrate later)
- `CampaignCreative.is_active` ORM/schema mismatch (deferred to migration track)
- 7 legacy BackendClient methods (dead code, unused by portal)
- `/deployment` page: demo-only (documentation, no backend data)
- `ScheduleConflict` ORM missing (legacy table)

---

### v0.11.1-pre-pilot-access-integration-hotfix (2026-06-16)

**Type:** Patch hotfix on v0.11.0.

**Includes:**
- v0.11.0-pre-pilot-security-baseline (full baseline)
- 40.2.1 — Admin Portal Access Bootstrap Fix (commit `5035203`)
  - Fix: PAGE_PERMISSION_MAP aligned with real backend permissions
  - 23 new backend seed integrity tests
- 40.2.2 — Portal Backend Integration Gate (commit `33d498c`)
  - Fix: /proof-of-play → production /api/reports/pop (was legacy test-kso)
  - 21 new guard tests (endpoint mapping + permission consistency)
  - Audited: 14 portal pages, 13 production, 1 fixed

**Regression:** 5168 passed, 44 skipped, 0 failed.

**Pilot Status:** NO-GO 🔴
- Scanner E2E: postponed (no hardware)
- Controlled long-run: not executed
- Gates B, C, D: documented, not executed

**Remaining Non-Blockers:**
- 7 legacy BackendClient methods (dead code, unused by portal)
- `/deployment` page: demo-only (documentation, no backend data)

---

### v0.11.0-pre-pilot-security-baseline (2026-06-16)

**Type:** Minor release.

**Includes:**
- 39.4 — Device/Sidecar Dashboard (aggregation endpoint, portal page, readiness)
- 40.0 — TZ Alignment / Security & RLS Audit
- 40.1 — RLS Hardening (foundation + gate closure)
- 40.2 — Admin Audit Hardening (business-audit trail, payload redaction)
- 40.3 — Pilot Readiness Gates Plan
- 40.4 — Baseline Regression Verification

**Regression:** 5156 passed, 32 skipped, 0 failed.

---

### v0.10.0-approval-publication-hardening (2026-06-26)

**Type:** Minor release.

**Includes:**
- 39.3 — Approval & Publication Hardening
- Production approval endpoints (create, approve, reject)
- Publication batch workflow
- Manifest generation and publish

**Regression:** 5058 passed.

---

### v0.9.0-product-portal-hardening (2026-06-26)

**Type:** Minor release.

**Includes:**
- 39.2 — Product Portal & Campaign Production API
- Production campaign endpoints (by-code CRUD)
- Production schedule endpoints
- Backend-driven dashboard with real KPI

**Regression:** 4976 passed.

---

## Earlier Milestones

Older milestones (v0.1.0–v0.8.0) documented in CHANGELOG.md. Retrospective tags only after explicit confirmation.
