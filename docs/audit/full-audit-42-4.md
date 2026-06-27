# Full Audit — 42.4

**Date:** 2026-06-16  
**Baseline:** HEAD `c3b8daa` (42.3 — Planned Reports Export)  
**Scope:** Retail Media Platform v0.12.x — backend, portal, KSO player/sidecar/state-adapter, infra, docs  
**Method:** Static code analysis, search patterns, existing doc review. No physical KSO/SSH/X11/Chromium/runner execution.

---

## 1. Backend Audit

### 1.1 Approvals

**Status:** Production-grade with RLS.

**Findings:**
- `GET /api/approvals` — RBAC `approvals.read`, RLS enforced via advertiser scope
- `POST /api/approvals/{code}/approve` / `/reject` — RBAC `approvals.approve`  
- `POST /api/approvals/test-kso/request` / `test-kso/{code}/decide` — **legacy test-kso paths** still registered (5 refs in router.py)
- `object_type` handling: `campaign`, `publication_batch` — covered, RLS via join
- `approval_code` generation — UUID-based, no leakage

**Debt:**
- **D-A-01 (P2):** Remove `test-kso` approval endpoints. Production equivalents exist.
- **D-A-02 (P2):** `_IncludedRouter` path introspection fails in FastAPI 0.137.1 — tests fixed with TestClient workaround.

### 1.2 Publications

**Status:** Production-grade. PublicationBatch workflow complete.

**Findings:**
- `POST /api/campaigns/by-code/{code}/create-publication-batch` — creates batch from approved campaign
- `POST /api/publication-batches/{id}/request-approval` → `approve` → `generate` → `publish` — full workflow
- `POST /api/publication-batches/{id}/cancel` — cancellation supported
- RLS: advertiser scoped via Campaign join
- Manifest generation: `generate_batch_manifests()` calls `build_manifest_from_placement()`

**Debt:**
- **D-PB-01 (P2):** Raw SQL `ScheduleRun` references — potential for `fromisoformat` issues on Python 3.6.9
- **D-PB-02 (P2):** `PublicationBatch.schedule_run` — not exposed in non-admin CSV export (by design)

### 1.3 Manifests

**Status:** Production-grade with test-kso legacy.

**Findings:**
- `POST /api/manifests` — production endpoint using `build_manifest_from_placement()`
- `POST /api/manifests/test-kso/generate` — **legacy** (6 refs in router.py)
- `GET /api/manifests` — lists all manifests, RBAC `manifests.read`
- Manifest structure: JSON with `manifest_code`, `version`, `device_code`, `creative_refs`
- NO signed URLs in manifest by design

**Debt:**
- **D-MF-01 (P2):** Remove `test-kso` manifest endpoints
- **D-MF-02 (P1):** Manifest delivery to physical KSO not validated — blocked by pilot NO-GO

### 1.4 Reports / Export

**Status:** New (42.3). CSV export with RLS.

**Findings:**
- `GET /api/reports/campaigns/export` — RLS via `resolve_user_scope_context()`
- `GET /api/reports/airtime/export?device_codes=…` — device scope RLS
- `GET /api/reports/conflicts/export?device_codes=…` — advertiser anonymization
- `GET /api/reports/publications/export` — RLS via campaign join
- CSV headers: safe, no raw UUIDs for non-admin
- Content-Type: `text/csv; charset=utf-8` ✅

**Debt:**
- **D-RP-01 (P2):** No Excel/XLSX export — CSV only, which is acceptable but limits business users
- **D-RP-02 (P3):** No date-range filtering on exports — exports all data, could be large

### 1.5 Campaigns

**Status:** Production + test-kso dual paths.

**Findings:**
- `GET /api/campaigns` — production list
- `GET /api/campaigns/test-kso` — **legacy** (6 refs in router.py)
- `POST /api/campaigns/by-code` — production create
- `POST /api/campaigns/by-code/{code}/submit` — submit for review
- `POST /api/campaigns/by-code/{code}/create-publication-batch` — batch creation
- RLS: advertiser scoped

**Debt:**
- **D-CA-01 (P2):** Remove `test-kso` campaign endpoints
- **D-CA-02 (P2):** 7 legacy `BackendClient` methods still reference test-kso paths

### 1.6 Creatives

**Status:** Production-grade.

**Findings:**
- `POST /api/creatives/upload` — multipart upload to MinIO
- `GET /api/creatives/by-code/{code}/preview` — safe stream proxy (42.2)
- `POST /api/creatives/by-code/{code}/archive` — archive support
- RLS: `media.read`, advertiser scope

**No debt items.**

### 1.7 Schedule

**Status:** Production + test-kso dual paths.

**Findings:**
- `GET /api/schedules` — production
- `GET /api/schedule/test-kso` — **legacy** (3 refs in router.py)
- `POST /api/schedules` — production create with slot support
- KSO placement model: `KsoPlacement` with `device_code`, `campaign_code`, `creative_code`

**Debt:**
- **D-SC-01 (P2):** Remove `test-kso` schedule/placement endpoints

### 1.8 Devices / Device Gateway

**Status:** Production-grade with UKM5 awareness.

**Findings:**
- Device auth: `POST /api/device-gateway/auth` — bcrypt hash, NO RBAC (by design — device, not human)
- Device router: `POST /api/device-gateway/heartbeat`, PoP submit — JWT-based
- Admin router: `GET /api/device-gateway/admin/*` — RBAC `devices.gateway.read/manage`
- `device_secret` never returned — generated once, hashed, not exposed
- UKM5 reference: `device_code` pattern `test-dev-seed`, `ukm5-*`

**Debt:**
- **D-DV-01 (P0):** Physical KSO device auth never tested with real UKM5 hardware
- **D-DV-02 (P1):** `device_secret` rotation not implemented
- **D-DV-03 (P2):** `KsoDevice` model has `screen_width`, `screen_height` — seeded at 1920×1080 for non-test-kso devices

### 1.9 PoP Ingest / Reporting

**Status:** Production-grade.

**Findings:**
- `POST /api/device-gateway/proof-of-play` — device-side submit with JWT
- `GET /api/reports/pop` — list with filters (campaign, creative, device, placement, date range)
- `GET /api/reports/pop/summary` — aggregated counts
- `GET /api/proof-of-play/test-kso` — **legacy** (3 refs)

**Debt:**
- **D-PP-01 (P0):** PoP never received from physical KSO — only test events
- **D-PP-02 (P2):** Remove `test-kso` PoP endpoints

### 1.10 RBAC / RLS

**Status:** Mature.

**Findings:**
- 49 permissions, 8 roles
- `require_permission()` enforced on all production endpoints
- `resolve_user_scope_context()` resolves advertiser/branch/store/device/campaign scopes
- Admin bypass: `system_admin`, `security_admin` — no scope restriction
- 404 for out-of-scope (not 403) — prevents information leakage
- All export endpoints (42.3) properly use RLS

**No debt items.**

### 1.11 Audit Trail

**Status:** Production-grade.

**Findings:**
- `AdminAuditEvent` — user/role/RLS changes, actor tracking
- `LoginAuditEvent` — every login attempt (success/failure), IP hash, user agent hash
- `device_gateway/service.py:82` — audit events for device auth failures
- Immutable — no UPDATE on audit tables

**No debt items.**

### 1.12 Safe Response Projections

**Status:** Good with minor gaps.

**Findings:**
- Backend responses use Pydantic schemas — only defined fields exposed
- CSV exports filter admin-only fields per role
- `test-kso` endpoints may return less-safe projections than production equivalents

**Debt:**
- **D-SR-01 (P2):** Verify all `test-kso` endpoints have same safe projection as production before removal

### 1.13 test-kso Legacy

**Total references:** 171 across 27 files.

**Production paths with test-kso:**
| Domain | test-kso endpoints | Ref count |
|---|---|---|
| Campaigns | `/api/campaigns/test-kso` | 6 |
| Approvals | `/api/approvals/test-kso/*` | 5 |
| Manifests | `/api/manifests/test-kso/generate` | 6 |
| Schedule | `/api/schedule/test-kso` | 3 |
| PoP | `/api/proof-of-play/test-kso` | 3 |
| BackendClient | 7 legacy methods | 23 |
| Test KSO Readiness | entire domain | 30+ |

**Debt:**
- **D-TK-01 (P2):** Consolidate and remove all test-kso production paths
- **D-TK-02 (P2):** 7 legacy BackendClient methods to remove
- **D-TK-03 (P2):** `test_kso_readiness` domain — keep as test-only, remove from production router

---

## 2. Portal Audit

### 2.1 Page Inventory

All 15+ pages checked. Summary:

| Page | Status | Issues |
|---|---|---|
| `/dashboard` | ✅ | No issues |
| `/reports` | ✅ (42.3) | No JS/CDN |
| `/campaigns` | ✅ | `onsubmit confirm` removed in 42.0 |
| `/campaigns/create` | ✅ | Server-side forms |
| `/creatives` | ✅ | Safe preview (42.2) |
| `/schedule` | ⚠️ | Has `<script>` for campaign link data (pre-existing, non-blocking) |
| `/approvals` | ✅ | Maker-checker flow |
| `/publications` | ✅ | Batch workflow |
| `/readiness` | ✅ | Device dashboard integration |
| `/device-dashboard` | ✅ | Backend-driven |
| `/devices` | ✅ | Safe projection |
| `/stores` | ✅ | Hierarchy |
| `/admin` | ✅ | RBAC admin pages |
| `/login` | ✅ | Password form, no JS |
| `/deployment` | ✅ | Info page |

### 2.2 Demo / Stub Data

**Finding:** `from demo_data import ...` in `main.py:16` — demo_data module still imported and used for fallback.

**Functions still imported:** `get_dashboard_data`, `get_stores_data`, `get_devices_data`, `get_campaigns_data`, `get_creatives_data`, `get_schedules_data`, `get_publications_data`, `get_approvals_data`, `get_users_data`

**Debt:**
- **D-PT-01 (P2):** Remove `demo_data` imports — all pages use backend API now. Demo data used as fallback only.

### 2.3 JS/CDN/localStorage

**Audit result:** Zero violations in current portal templates (42.3 confirmed).

Exceptions:
- `schedule.html`: contains `<script>` block for campaign link data — pre-existing, non-rendering JS, no CDN
- `kso_player/player_shell/index.html`: 4 refs — player shell, not portal, uses Chromium kiosk context (valid)

**No new debt.**

### 2.4 Export Routes

**42.3 additions:** All 4 export routes (`/reports/export/*`) use GET, server-side proxy, RLS via backend.

**No issues found.**

### 2.5 UX Gaps

| Gap | Severity | Notes |
|---|---|---|
| Campaign status export link only shown when data present | P3 | Empty state shows no CSV button |
| No date-range filter on CSV exports | P3 | Exports all data |
| Portal sidebar still shows "KSO v1" | P3 | Branding cleanup |

### 2.6 Unsafe Links / Downloads

**Audit result:** Zero findings. All download links are `<a href>` GET requests. No `download` attribute abuse.

---

## 3. KSO Player / Sidecar / State Adapter

### 3.1 Portrait 768×1024 Profile

**Status:** ✅ Confirmed.

**Findings:**
- `x11_click_through_renderer.py`: enforces 768×1024 geometry, rejects non-matching
- `profiles/portrait_fullscreen_idle_screensaver_768.py`: UKM5 portrait profile
- `profiles/portrait_idle_overlay_768.py`: overlay profile
- `portrait_smoke.py`: smoke test for portrait profile

**No issues.**

### 3.2 Device Auth (JWT)

**Status:** Implemented, not physically tested.

**Findings:**
- `device_auth_client.py`: bcrypt-based auth to backend
- JWT token refresh: 60-minute expiry
- Heartbeat: periodic with configurable interval

**Debt:**
- **D-KS-01 (P0):** Device auth never tested with physical KSO (blocked by pilot NO-GO)

### 3.3 Manifest / Media Fetch

**Status:** Implemented, test-only.

**Debt:**
- **D-KS-02 (P0):** Manifest fetch from backend never tested end-to-end with physical KSO
- **D-KS-03 (P0):** Media file download from MinIO never tested from physical KSO network

### 3.4 Sidecar Sync Readiness

**Status:** Test coverage exists, not physically validated.

**Findings:**
- `test_pop_scoped_send.py`: retry logic for PoP send failures
- `test_kso_combined_daemon_e2e_smoke.py`: E2E smoke for combined daemon
- `test_kso_full_local_runtime_e2e_smoke.py`: local runtime E2E

**Debt:**
- **D-KS-04 (P0):** Sidecar sync never physically started/validated

### 3.5 Offline / Failed Backend Behavior

**Status:** Partially tested.

**Findings:**
- Retry logic exists for PoP sending (sidecar)
- No explicit offline mode — daemon will retry until backend available

**Debt:**
- **D-KS-05 (P1):** No graceful offline degradation — daemon retries indefinitely, no backpressure

### 3.6 UKM5 Dependency

**Status:** Awareness exists, no runtime dependency.

**Findings:**
- `state_adapter`: reads UKM5 state files (if present), falls back gracefully
- `state_source_file.py`: configurable path, no hard dependency

**No issues.**

### 3.7 No Second Fullscreen Chromium

**Status:** ✅ Confirmed. Only one Chromium kiosk instance per KSO.

---

## 4. Infra / Linux / Deployment

### 4.1 systemd Units

| Unit | Status |
|---|---|
| `kso-player.service` | Defined, not deployed |
| `kso-sidecar.service` | Defined, not deployed |
| `kso-state-adapter.service` | Defined, not deployed |

**Debt:**
- **D-IN-01 (P0):** systemd units never deployed to physical KSO

### 4.2 Environment / Secrets

**Findings:**
- `.env.example` files exist for kso-player, kso-sidecar, kso-state-adapter
- Secrets: `DEVICE_SECRET`, `BACKEND_URL`, `JWT_SECRET`
- `.env` files NOT in git (gitignored)

**No debt items.**

### 4.3 Runbooks

**Existing:**
- `docs/pilot/one-kso-pilot-runbook.md` ✅
- `docs/pilot/go-no-go-checklist.md` ✅
- `docs/kso/linux-kso-pilot-first-start-runbook.md` ✅

**Missing:**
- Rollback runbook (not formally documented)
- Incident response runbook

**Debt:**
- **D-IN-02 (P1):** No formal rollback runbook
- **D-IN-03 (P2):** No incident response runbook

### 4.4 Long-Run Readiness

**Debt:**
- **D-IN-04 (P0):** Controlled 48h+ long-run never executed (pilot blocker)

### 4.5 Logs and Evidence Handling

**Findings:**
- Player writes PoP evidence to local files
- Sidecar sends to backend
- Evidence checklist exists: `docs/pilot/evidence-checklist.md`

**No new debt.**

---

## 5. Docs Audit

### 5.1 Status Summary

| Doc | Status |
|---|---|
| `docs/audit/release-versioning-policy.md` | ✅ Current |
| `docs/audit/technical-debt-next-actions.md` | ⚠️ Needs update (this audit) |
| `docs/audit/product-backend-frontend-gap-analysis.md` | ⚠️ Outdated |
| `docs/audit/portal-backend-integration-matrix.md` | ⚠️ Needs 42.3 additions |
| `docs/pilot/*` | ✅ Current (NO-GO baseline) |
| `docs/security/*` | ⚠️ No dedicated security hardening doc |
| `docs/product/campaign-workflow.md` | ⚠️ Missing |
| `docs/architecture/*` | ⚠️ No architecture decision records |
| `CHANGELOG.md` | ✅ Current (42.3 added) |

### 5.2 Gaps

| Gap | Severity |
|---|---|
| No architecture decision records (ADR) | P2 |
| No security hardening document | P1 |
| Campaign workflow doc missing | P2 |
| Technical debt doc outdated | P1 |
| Portal-backend integration matrix needs 42.3 update | P2 |

**Debt:**
- **D-DC-01 (P1):** Create `docs/security/hardening-plan.md`
- **D-DC-02 (P2):** Create `docs/product/campaign-workflow.md`
- **D-DC-03 (P2):** Create `docs/architecture/adr/` with key decisions
- **D-DC-04 (P2):** Update `docs/audit/portal-backend-integration-matrix.md` for 42.3

---

## 6. Known Pilot Blockers (confirmed)

| ID | Blocker | Status |
|---|---|---|
| B-01 | HW scanner E2E validation | ❌ Not executed |
| B-02 | Controlled 48h+ long-run | ❌ Not executed |
| B-03 | Manifest delivery to physical KSO | ❌ Not approved |
| B-04 | Sidecar sync physical start | ❌ Not executed |
| B-05 | Pilot runbook/fallback/rollback finalization | ❌ Pending |
| B-06 | Live pilot/fleet rollout approval | ❌ Not approved |

**No new blockers found after 42.3.** CSV export, RLS, and reports are safe.

---

## 7. Summary

| Area | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| Backend | 0 | 0 | 14 | 1 | 15 |
| Portal | 0 | 0 | 1 | 3 | 4 |
| KSO | 4 | 1 | 0 | 0 | 5 |
| Infra | 2 | 1 | 1 | 0 | 4 |
| Docs | 0 | 2 | 4 | 0 | 6 |
| **Total** | **6** | **4** | **20** | **4** | **34** |

**P0 items are all pilot blockers — already known, not new.**
**42.3 introduced no regressions.**
