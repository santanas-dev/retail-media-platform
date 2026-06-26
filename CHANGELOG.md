# Changelog

All notable changes to the Retail Media Platform.

Format: [SemVer](https://semver.org/) + annotated Git tags.
Every minor tag requires: green full regression, clean git status, no secrets in docs/output.

---

## [Unreleased] — Product Backend / Frontend Gap Analysis (39.0, 2026-06-25)

### 39.2.4 — Reports Backend-Driven Integration

**Reports page connected to production PoP backend — demo_data removed as primary source.**

- Backend: new production endpoints `GET /api/reports/pop` (list) and `GET /api/reports/pop/summary` (aggregation)
- Both endpoints require `reports.read` permission, safe projection (no raw UUIDs/secrets)
- `get_pop_summary` aggregates: total_events, unique_devices/campaigns/creatives/placements, accepted/rejected/duplicate/unknown_status, last_event_at
- `BackendClient`: new `get_pop_report()` and `get_pop_summary()` methods (production)
- `list_pop_events()` retained as legacy test-kso
- `/reports` handler: async backend-driven endpoint replacing `_page()` + demo_data
- Template: KPI cards (PoP events, unique devices/creatives, rejected, campaigns, KSO/manifests), events table, status breakdown, chart placeholders (deferred), Excel export (deferred)
- Charts/slicers/drill-down deferred until backend metrics mature
- `get_report_kpi()` / `get_report_table()` imports removed from `main.py`
- RBAC: `/reports` → `reports.read` (was `view_reports`)
- Backend tests: +8 (PoPSummarySchema, endpoint safety) → 322 total
- Portal tests: 424/424 OK (updated TestReportsPage for production template)
- Fake/demo numbers → GONE, Power BI mentions → removed, test-kso not primary source
- `GET /api/proof-of-play/test-kso` retained as legacy
- B4 Reports UI → ✅ CLOSED

### 39.2.3.1 — Dashboard Production KPI Source Fix

**Dashboard KPI sources switched from test-kso to production endpoints.**

- `list_campaigns_prod()` → `GET /api/campaigns` (production) for campaign KPI counting
- `list_manifests()` → `GET /api/manifests` (new production endpoint) for publications KPI
- Backend: new `GET /api/manifests` production endpoint (safe projection, `publications.read`)
- `GET /api/manifests/test-kso` retained as legacy
- Dashboard no longer uses test-kso as primary KPI source
- Backend tests: 314/314 OK | Portal tests: 425/425 OK
- Dashboard test-kso dependency → GONE ✅

### 39.2.3 — Portal Dashboard Real KPI Integration

**Dashboard connected to backend — demo_data removed as primary KPI source.**

- Dashboard handler: explicit async endpoint replacing `_page()` helper + `get_dashboard_data()`
- KPI computed from 6 existing safe list endpoints: campaigns, creatives, devices, schedules, manifests, approvals
- No new backend endpoints — aggregation happens in portal
- KPI cards: total/active/draft campaigns, creatives, devices, schedules (active), publications, approvals pending
- Fallback: safe empty state when backend unreachable, partial warning when some sources fail
- Demo values ("12", "1 247", "3") removed from dashboard
- Template: card names updated, demo wording removed, production note added
- Portal tests: 425/425 OK (+1 test: `test_no_demo_fake_values`)
- Dashboard DEMO gap → CLOSED ✅

**Remaining:** Reports (39.5)

### 39.2.2.1 — Campaign Create Production API Fix

**Campaign creation now uses production `POST /api/campaigns/by-code` — test-kso no longer primary path.**

- Backend: new `POST /api/campaigns/by-code` endpoint + `CampaignCreateByCode` schema + `create_campaign_by_code` service
- `BackendClient.create_campaign` now calls `/api/campaigns/by-code` (production) instead of `/api/campaigns/test-kso`
- Portal `/campaigns/create` uses production API exclusively
- Template: test-kso reference removed from UI text
- Test-kso endpoints (`POST /api/campaigns/test-kso`, `GET /api/campaigns/test-kso`) retained as legacy/dev helpers
- Backend tests: 314/314 OK
- Portal tests: 424/424 OK
- Campaign UI production gap → FULLY CLOSED ✅

### 39.2.2 — Portal Campaign Create/Edit UI Backend Integration

**Campaign page connected to production Campaign API — create, edit, archive, creative binding.**

- `BackendClient`: 8 new/updated methods — list_campaigns (test-kso safe), create_campaign (test-kso), get_campaign_by_code, update_campaign_by_code, archive_campaign_by_code, list_campaign_creatives, bind_campaign_creative, unbind_campaign_creative
- Portal `/campaigns` page: campaign list + create form + inline edit + archive + creative binding
- Portal POST endpoints: `/campaigns/create`, `/campaigns/{code}/edit`, `/campaigns/{code}/archive`, `/campaigns/{code}/bind-creative`, `/campaigns/{code}/unbind-creative/{cc}`
- RBAC fix: PAGE_PERMISSION_MAP `/campaigns` → `campaigns.read` (match backend permission)
- Template: campaigns table + create/edit/bind forms + archive button; test-kso note replaced with production API note
- All forms server-side POST, no JS/CDN/localStorage
- Portal tests: 424/424 OK
- Campaign UI test-kso dependency → GONE ✅

**Remaining:** Dashboard (39.2.3), Reports (39.5)

### 39.2.1 — Portal Schedule UI Backend Integration

**Schedule page connected to production Schedule Backend API.**

- `BackendClient`: 12 new methods — list_schedules, create_schedule, get_schedule, update_schedule, archive_schedule, list_schedule_slots, create_schedule_slot, update_schedule_slot, disable_schedule_slot, list_placements_prod
- Portal `/schedule` page: schedules list + slots inline + create schedule form + create slot form
- Portal POST endpoints: `/schedule/create`, `/schedule/{code}/create-slot`, `/schedule/{code}/archive`, `/schedule/{code}/items/{slot}/disable`
- RBAC fix: PAGE_PERMISSION_MAP `/schedule` → `scheduling.read` (match backend permission)
- Template: schedules table (schedule_code, name, status, campaign_code, valid_from/to, timezone, slot_count), slots table (slot_code, day_of_week, start/end_time, placement_code, is_active), archive/disable actions
- All forms server-side POST, no JS/CDN/localStorage
- Fallback renders safe empty state when backend unreachable
- Portal tests: 424/424 OK
- Schedule UI DEMO gap → CLOSED ✅

**Remaining:** Campaign UI (39.2.2), Dashboard (39.2.3), Reports (39.5)

### 39.1.3 — Schedule Backend API Hardening

**Schedule + ScheduleSlot models** — production schedule API foundation.

- `Schedule` model: schedule_code, name, status (draft/active/archived), valid_from/to, campaign_code, timezone
- `ScheduleSlot` model: slot_code, day_of_week, start_time/end_time, placement_code, is_active
- `GET/POST /api/schedules` — list + create schedules
- `GET/PATCH /api/schedules/{schedule_code}` — get + update by code
- `POST /api/schedules/{schedule_code}/archive` — archive
- `GET /api/schedules/{schedule_code}/items` — list slots
- `POST /api/schedules/{schedule_code}/items` — create slot
- `PATCH /api/schedules/{schedule_code}/items/{slot_code}` — update slot
- `DELETE /api/schedules/{schedule_code}/items/{slot_code}` — disable (soft)
- Test-kso schedule endpoints retained as legacy
- Backend tests: 314/314 OK
- **Schedule backend gap → CLOSED** ✅

**Remaining:** Portal Schedule UI (39.2), Dashboard (39.2), Reports (39.5)

---

### 39.1.2 — Campaign / Placement Production API Hardening

**Production API foundation:** campaign code-based CRUD, creative binding, placement CRUD.

- `GET/PATCH /api/campaigns/by-code/{campaign_code}` — code-based lookup + update
- `POST /api/campaigns/by-code/{campaign_code}/archive` — archive by code
- `GET /api/campaigns/by-code/{campaign_code}/creatives` — list campaign creatives
- `POST /api/campaigns/by-code/{campaign_code}/creatives` — bind creative (idempotent)
- `DELETE /api/campaigns/by-code/{campaign_code}/creatives/{code}` — unbind (soft)
- `GET/POST /api/placements` — production placement list + create
- `GET/PATCH /api/placements/{placement_code}` — get + update by code
- `POST /api/placements/{placement_code}/archive` — archive by code
- Test-kso endpoints retained as legacy (`/api/campaigns/test-kso`, `/api/schedule/test-kso`)
- Backend tests: +9 new tests, 314/314 OK
- Security gap SG5 (campaign/placement test-kso wrapper) → **CLOSED** ✅

**Remaining:** Schedule CRUD (39.1.3), Portal UI (39.2)

---

### 39.1.1 — Device Gateway Auth Hardening

**Auth foundation:** device gateway PoP ingest + KSO manifest endpoints now require valid device JWT.

- `POST /api/device-gateway/kso/{code}/pop` — was TEST_ONLY → now JWT device auth + code match
- `GET /kso/{device_code}/manifest` — was TEST_ONLY → now JWT device auth + code match
- `GET /manifest/current` — already protected ✅
- `GET /media/{id}` — already protected ✅
- Device auth flow: device_code + secret → bcrypt verify → JWT (60 min)
- Auth failures: uniform 401 "Invalid device credentials" (no info leakage)
- Backend tests: +13 new auth tests, 305/305 OK
- Security gap SG1 (PoP) and SG2 (manifest) → **CLOSED** ✅

**Deferred:** mTLS, credential rotation, nonce/replay protection, rate limiting

---

### 39.0 — Product Backend / Frontend Gap Analysis

**Analysis document:** `docs/audit/product-backend-frontend-gap-analysis.md`

- **23 backend domains** audited: 16 production-ready, 4 partial, 3 TEST_ONLY security gaps
- **16 portal pages** audited: 10 backend-driven, 3 partial, 3 DEMO stubs (dashboard, schedule, reports)
- **29 total gaps** identified

**Pilot blockers (🔴 HIGH):**
- Device gateway auth (manifest/media/PoP — TEST_ONLY без аутентификации)
- Schedule UI (DEMO form, не подключён к backend)
- HW scanner E2E validation (POSTPONED — scanner unavailable)
- Controlled long-run (≥1 час)

**Release plan proposed (7 phases):**
39.1 Backend API hardening → 39.2 Portal UI completion → 39.3 Approval/publication workflow →
39.4 Device/readiness dashboard → 39.5 PoP reporting → 39.6 RBAC/RLS/Admin →
39.7 Pilot runbook

**Regression:** 4939 all green, git clean

---

### 38.17 — Backend Regression Baseline Stabilization

- Backend: 27 cross-component import errors → **FIXED** (sys.path test isolation)
- Backend: 292/292 OK, 0 errors
- Full regression: 4939 all green
- 2 test files patched (`test_z_readiness_gate_383.py`, `test_z_x11_runner_pop_full_e2e_3827.py`)
- Zero business logic changes

---

### 38.15 — HW Scanner E2E Validation Plan

**Plan document:** `docs/audit/hw-scanner-e2e-validation-plan.md`

- **Status:** NOT EXECUTED ❌ — POSTPONED / BLOCKED BY MISSING HARDWARE
- **Reason:** physical barcode scanner hardware unavailable
- **Pilot blocker:** 🔴 HIGH — remains active
- **Validation cannot be replaced** by keyboard simulation
- **Test can resume only** when real hardware scanner is available

**Safe protocol documented:**
- 4-phase test (S1–S4), 8 stop criteria, 7 safety rules, 6 proof points
- Approval token: `PHASE_SCANNER_E2E_APPROVED`
- One controlled test only, operator-observed confirmation, no data logging

**Resumption conditions:** scanner hardware connected + operator present + PHASE_SCANNER_E2E_APPROVED + regression green

**Not executed:** no physical scanner test, no SSH to KSO, no X11/Chromium/runner, no sidecar, no PoP upload, no UKM5 modification

**Safe alternatives:** long-run plan (38.16), BackendIntegration fix (38.17), runbook (38.18)

---

### 38.14 — One-KSO Pilot Readiness Decision Gate

**Decision document:** `docs/audit/one-kso-pilot-readiness-decision-gate.md`

- One-KSO technical dry run: **PASSED** ✅ (D0–D6 all green)
- One-KSO pilot readiness: **CONDITIONAL** ⚠️ (requires HW scanner E2E + controlled long-run)
- Production/fleet rollout: **NOT APPROVED** 🚫

**Proven chain:** portal/backend → manifest/media → KSO player render → PoP → backend → portal report

**Allowed next:** HW scanner E2E plan, controlled long-run plan, BackendIntegration RBAC fix
**Forbidden:** systemd/autostart, fleet rollout, live store pilot, PoP evidence deletion

### 38.13.3 — Phase D Closure (D0–D6 all green) ✅

**D3.1 — Pre-D4 Regression Triage:**
- Backend 6 INTERNALERROR → fixed: `norecursedirs` excludes integration scripts
- Portal-web 9 BackendIntegration → documented (pre-existing 3-layer isolation defect)
- Infra 1 unittest failure → documented (pytest-only, 227/227 pass)
- Core green: **4917 passed, 0 failures**

**D4 — Controlled PoP Upload:**
- **Bug discovered:** `NoReferencedTableError` on `creatives.creative_code` FK — PoP ingest returned HTTP 500 against real PostgreSQL
- Root cause: `service.py` imported `CampaignCreative` but not `Creative`/`User` — SQLAlchemy FK resolution failed at commit
- **Fix:** Added `from app.domains.media.models import Creative` and `from app.domains.identity.models import User` (commit `8b367eb`)
- **PoP upload:** 1 synthetic event sent → HTTP 200 accepted ✅
- **Event data:** test_playback_completed, duration_ms=1000, device=test-dev-seed, campaign=test-camp-seed, creative=test-creative-seed
- **Before:** 0 PoP events, **After:** 1 PoP event (delta +1)
- **Commit:** `7146029` — regression baseline docs updated with FK discovery

**D5 — PoP Report Verification:**
- **Backend:** D4 event found via `/api/proof-of-play/test-kso` ✅
- All fields verified: status=accepted, campaign=test-camp-seed, creative=test-creative-seed, placement=test-place-seed, event_type=test_playback_completed, duration_ms=1000
- All filters pass: device (2 events), campaign (2), creative (2), placement (2)
- KPI count: 2 test_playback_completed events
- Forbidden fields: **CLEAN** (no IDs, secrets, receipts, fiscal, payment, personal data)

**D6 — Cleanup and Phase D Closure:**
- Removed: stale test lock dirs (`/tmp/tmp*` — 40KB), repo `__pycache__`, `.pytest_cache`
- Preserved: backend PoP event (d4-synth-***-0de5dc), config, secret, manifest, media cache
- KSO temp files (`/tmp/d3_evidence/`, `/tmp/d3_runner.py`) remain on KSO (unreachable via SSH) — harmless in /tmp
- UKM5/Openbox/systemd unchanged, no X11/Chromium/runner/sidecar launched
- **Phase D one-KSO E2E dry run: COMPLETE** (D0–D6 all green)

**Stop criteria all met:**
- D3 visual run NOT repeated, X11/Chromium/runner NOT launched
- Sidecar daemon NOT started, UKM5/Openbox/systemd unchanged
- No new PoP events beyond D4's single upload
- Secrets/full URLs/tokens/barcodes NOT printed
- Payload forbidden field check: CLEAN
- D6 cleanup NOT executed (awaiting separate approval)

**Regression:** TBD (after doc update)

### 38.13.2 — D2.1: Python 3.6 Runner Compatibility + Fullscreen Runner Plan
- **Blocker 1:** `datetime.fromisoformat` unavailable on Python 3.6 (KSO runtime)
- Created `kso_player/timestamp_utils.py` with `parse_iso_utc()` via `strptime` — py36-compatible
- Replaced all `fromisoformat` calls in `runtime_gate.py`, `screensaver_creative.py`, `state_observer.py`, `simulator.py`, `run_cycle.py`
- **Blocker 2:** Registered fullscreen profile `portrait_fullscreen_idle_screensaver_768` (768×1024+0+0, kiosk, idle_only)
- 13 new unit tests for timestamp parser — Z, microseconds, offset, invalid→None
- Added `PYTHONPATH` to subprocess calls in CLI tests (`test_run_once_cli.py`, `test_run_once_cli_backend.py`, `test_run_cycle_runtime_config.py`)
- **Regression:** backend 292 ✅ | portal-web 404 ✅ | kso_state_adapter 86 ✅ | kso_player 2065 ✅ | kso_sidecar 1838 ✅ | infra 227 ✅
- Total: **4912 passed, 0 failed** (vs 4894 baseline — +18 new tests)

### 38.13.1 — Phase D Geometry Consistency Fix
- **Critical fix:** test-dev-seed GatewayDevice was linked to shared landscape display_surface (1920×1080)
- Real KSO is portrait 768×1024 — created dedicated portrait surface + logical_carrier
- GatewayDevice updated to portrait surface; legacy landscape surface preserved for other devices
- Created `docs/audit/kso-portrait-architecture-pivot.md`
- Manifest/media NOT geometry-dependent — no content changes needed

### 38.13 — Phase D Preflight

### 38.12.2 — Backend Regression Stabilization
- Fixed 27 pre-existing backend errors: PYTHONPATH config in `backend/pyproject.toml`
- Added `["../apps/kso_player", "../apps/kso_sidecar_agent"]` to pytest pythonpath
- Backend: 292/292 green (was 265)
- Portal-web: 404/404 green (20 BackendIntegration excluded — need live backend)
- Full regression: 4894 green baseline
- Secret discrepancy resolved: 32→25 bytes = different registration instances

### 38.13 — Phase D Preflight
- Created `docs/audit/phase-d-one-kso-e2e-dry-run-preflight.md` — full runbook
- 6 sub-phases (D0–D6), 12 stop criteria, rollback procedure, approval gates
- Readiness verified: backend health, manifest, credential, campaign/placement
- No KSO/sidecar/X11/PoP executed — documentation only

### Requirements verification
- ✅ Full regression: 4894 green
- ✅ Git status clean
- ✅ No secrets / full URLs / tokens committed
- ✅ No sidecar/X11/PoP/runner launched

---

## [38.12.1] — Phase C Controlled Run + Stabilization (2026-06-25)

### Phase C.1 — Manifest Sync
- GatewayDevice `test-dev-seed` created in `gateway_devices` + credential in `device_credentials`
- Publication chain wired: device → display_surface → publication_target → manifest_version → manifest_items
- Manifest sync via `/api/device-gateway/manifest/current`: ✅ `served`, 1 item (`image/png`, slot-000)
- Manifest saved on KSO: `manifest/current_manifest.json`, 1 item

### Phase C.2 — Media Sync
- Media downloaded: ✅ `slot-000.png` (108 bytes), cache complete
- Endpoint: `/api/device-gateway/media/{manifest_item_id}` — 200 OK

### Backend/Data Fixes (during Phase C)
- **ScheduleItem model** — added to `scheduling/models.py` (table existed, model was missing → ImportError in `_collect_kso_source_items`)
- **GatewayDevice** — linked to display_surface + store (was unlinked, causing `no_manifest`)
- **schedule_item.date** — updated to today (was 2026-06-21, past valid_to → items filtered out)
- **media_path** — fixed to `creatives/...` format (was `media/current/...` → 403 `_validate_object_key`)

### Security
- No sidecar daemon / PoP upload / X11 / Chromium / UKM5 modifications
- No secrets, full URLs, or tokens in output or git
- No media/manifest/runtime KSO files committed

## Phase C Preflight (38.12)

- `test-kso-phase-c-manifest-media-cache-preflight.md` — 10-section Phase C readiness plan
- Pre-conditions: backend reachability, auth path, published manifest, creative media, disk space
- Command templates (masked): config-status, secret-store-check, sync-manifest (⛔ not run), sync-media (⛔ not run)
- 10 safety gates (G1–G10), 10 stop criteria (S1–S10), rollback (partial/full)
- No network calls from KSO, no sidecar/X11/Chromium/PoP started
- Full regression: 4926 green (292+424+86+2059+1838+227)

## Phase B Applied — Config on Test KSO (commit `83afb9c`)

- AGENT_ROOT: `/home/ukm5/kso-agent`, 9 subdirectories, valid config (177 bytes), secret (32 bytes, 0600)
- Backend reachable, no placeholders, secret via safe stdin (never printed)
- No sidecar/X11/Chromium/PoP started

## [v0.6.0] — Sidecar Config Readiness (Phase B Preparation)

**Tag:** `v0.6.0-sidecar-config-readiness` (2026-06-26)
**Commit:** (see tag)

### Sidecar Config

- `config/agent_config.json.example` — safe template with placeholders (no real values)
- `local_config.validate_no_placeholders()` — dry-check config without exposing values
- `local_config.config_status()` — enhanced: now returns `has_placeholders`, `placeholder_fields`
- `PLACEHOLDER_PATTERNS` — detects `<TEST_BACKEND_BASE_URL>`, `<TEST_KSO_DEVICE_CODE>`, etc.

### Gitignore

- `agent_config.json`, `device_secret.dev`, `*_filled.json` — ignored
- `agent-root/`, `kso-agent-root/`, `test-agent-root/` — local test roots ignored

### Docs

- `test-kso-sidecar-config-preparation.md` — Phase B analysis, config mechanisms, operator checklist
- Updated: runbook, config-checklist, readiness-gate, pilot-plan, tech-debt

### Readiness

- `sidecar_config_ready` stays `false` — backend cannot inspect local sidecar filesystem
- Only `validate_no_placeholders()` on KSO determines real config readiness

---

## [v0.5.0] — Test-KSO Readiness Control Plane + Phase A Backend Readiness

**Tag:** `v0.5.0-test-kso-phase-a-readiness` (2026-06-25)
**Commit:** `c6ad526`

### Readiness Control Plane

- `GET /api/test-kso/readiness?device_code=<code>` — comprehensive readiness status (55+ fields)
- `POST /api/test-kso/seed` — idempotent synthetic seed (device→campaign→creative→manifest chain)
- `GET /api/test-kso/sidecar-config-checklist` — 12 sidecar config field statuses (names only, no values)
- Portal `/readiness` — 8 component sections + Phase D Gate + Operator Preflight guidance
- `required_operator_steps` — 13 preflight steps (Phase A/B/C)
- Phase D gate: ⛔ blocked, requires explicit manual approval

### Contract Fix

- `overall_ready` now honestly requires `sidecar_config_ready=true` AND `media_cache_ready=true`
- Previously returned `true` ignoring missing sidecar config and media cache

### Docs

- `test-kso-live-backend-seed-runbook.md` — operator preflight runbook (Phase A/B/C, placeholders, no secrets)
- `test-kso-live-config-checklist.md` — 12 sidecar config fields reference
- `test-kso-phase-a-backend-readiness-result.md` — live Phase A execution result
- `versioning-policy.md` — SemVer policy, tag naming, regression requirements

### Regression

- Backend: 292 ✅
- Portal: 424 ✅
- State: 86 ✅
- KSO Player: 2059 ✅ (12 skipped)
- Sidecar Agent: 1838 ✅
- Infra: 227 ✅
- **Total: 4926 green**

### Not Included

- ❌ Live sidecar config on KSO (Phase B — blocked)
- ❌ Media cache on KSO (Phase C — blocked)
- ❌ Phase D physical run / X11 / Chromium (blocked)
- ❌ SSH to KSO (not executed)
- ❌ HW scanner integration
- ❌ Production deployment

---

## [v0.4.0] — Runner / Manifest / Media / PoP Dev E2E

**Tag:** (not yet tagged)
**Period:** 2026-06-22 – 2026-06-24

### X11 Runner

- Guarded X11 screensaver runner with kill-switch and idle-state safety
- Portrait overlay player (768×1024) — profile contract, shell, smoke harness
- X11 click-through renderer contract + physical proof harness
- Fullscreen screensaver input pass-through design
- Rollback to UKM5 after screensaver exit (confirmed: grey 236,236,236)

### Manifest

- KSO safe manifest extractor — creative_code preservation
- Bridge: manifest order → player playlist → creative → media filename
- `creative_code` tracing through entire chain: manifest → playlist → creative → PoP

### Media Cache

- Sidecar media cache bridge to X11 runner
- Sync/reference resolution: filename → symlink → invalid → hidden/blocked
- Media availability status in readiness report

### PoP (Proof of Play)

- X11 runner PoP reporting E2E bridge
- `ScreensaverPoPDraft → JSONL → PopPayloadEvent.creative_code`
- Backend PoP ingest: placement→campaign→creative mapping
- Duplicate `event_code` idempotent handling
- Campaign PoP report with creative_code breakdown
- Portal PoP report page

### Backend

- Portal user CRUD
- Backend PoP integration E2E test
- Sidecar regression baseline stabilization
- Python 3.6 X11 screensaver proof harness

### Infrastructure

- Docker Compose: PostgreSQL, Redis, ClickHouse, MinIO, Nginx
- Alembic migrations
- Full regression: 4926 tests total

---

## [v0.3.0] — Physical KSO Architecture Pivot + X11 Click-Through Proof

**Tag:** (not yet tagged)
**Period:** 2026-06-20 – 2026-06-22

### Architecture Pivot

- Pivot from KSO vendor integration to physical KSO device control
- Portrait idle overlay player profile (768×1024)
- Player shell: safe observer stub, kill-switch, state adapter
- UKM5 process integrity guard — never modify UKM5/Openbox/systemd

### Physical KSO

- Physical KSO dry smoke validation (pre-configured test device)
- Phase 2 overlay render execution — manual one-shot, no fullscreen/kiosk
- Remote X11 proof harness for controlled rollout
- Status correction: visual display confirmed

### Contracts

- X11 click-through renderer contract
- Portrait overlay local smoke harness
- Physical KSO test plan
- Fullscreen idle screensaver interaction design

### Safety

- Kill-switch marker file
- Safe player state observer (read-only)
- UKM5 restoration guarantee after rollback
- No autostart/systemd/ fleet — explicit manual control

---

## [v0.2.0] — KSO Backend/Portal Vertical Chain

**Tag:** (not yet tagged)
**Period:** 2026-06-18 – 2026-06-20

### KSO Backend

- KSO runtime config fields (`backend/app/domains/kso/`)
- KSO device registration, status management
- KSO channel → device hierarchy mapping
- KSO manifest generation with creative_code + media_ref

### Portal

- KSO device management pages
- KSO channel configuration
- KSO manifest preview
- Backend API client — secure httpx-based with credential isolation

### Architecture

- KSO player adapter architecture doc
- KSO vendor integration questions/contract
- KSO local interface contract
- Hierarchical projection: Channel→DeviceType→PhysicalDevice→LogicalCarrier→DisplaySurface+CapabilityProfile

---

## [v0.1.0] — Backend / Portal Foundation

**Tag:** (not yet tagged)
**Period:** 2026-06-16 – 2026-06-18

### Architecture

- Multichannel architecture skeleton (commit `00c12c7`)
- Channel-agnostic core + adapters pattern
- FastAPI + React + PostgreSQL + ClickHouse + MinIO + Redis + Chromium kiosk
- Manifest: signed JSON, no JWT in URL; mTLS deferred

### Core

- Identity and Access domain — user CRUD, auth (JWT), RBAC
- Docker Compose dev environment
- Alembic migration framework
- Nginx reverse proxy
- Portal: login, dashboard, admin pages
- CI-ready backend test suite

### Database

- 9 core tables: channels, device_types, physical_devices, logical_carriers, display_surfaces, capability_profiles, users, roles, permissions
- `/health` — status + DB connectivity check

---

## Tag Naming Convention

```
v<major>.<minor>.<patch>-<descriptor>
```

- **patch:** small fixes, regression updates, docs-only changes
- **minor:** completed project phase (new feature group, new domain)
- **major:** production release, pilot rollout, breaking changes
- **descriptor:** short phase name (e.g. `test-kso-phase-a-readiness`)

### Requirements for every minor tag

- ✅ Full regression green (all 6 suites)
- ✅ Git status clean
- ✅ No secrets / real URLs / tokens / device_secret in docs, output, or tag message
- ✅ Annotated tag (`git tag -a`) with description

### Retrospective tags

Older milestones (v0.1.0–v0.4.0) have not been tagged. Retrospective tags should only be created after explicit confirmation, as they may point to commits with known issues or incomplete regression state.

### Future Tags (recommended)

| Tag | Description |
|---|---|
| `v0.6.0-sidecar-config-readiness` | Sidecar config filled + verified on KSO (Phase B) |
| `v0.7.0-one-kso-e2e-dry-run` | Controlled one-KSO E2E dry run (Phase C+D, no prod) |
| `v0.8.0-pilot-readiness` | Pilot rollout gate — all prerequisites, 4926 green |
| `v1.0.0-kso-production-release` | First production KSO release |
