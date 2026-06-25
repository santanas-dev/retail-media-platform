# Changelog

All notable changes to the Retail Media Platform.

Format: [SemVer](https://semver.org/) + annotated Git tags.
Every minor tag requires: green full regression, clean git status, no secrets in docs/output.

---

## [Unreleased] — Phase D Preflight (38.13, 2026-06-25)

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
