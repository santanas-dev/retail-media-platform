# Technical Debt — Next Actions

> **Статус:** 📋 Action Plan (37.14)
>
> Дата: 2026-06-16
> Ревизия: 9 (38.1 — physical KSO Phase 0–1 dry smoke executed)
>
> **Принцип:** Не закрывать весь долг сейчас. Закрывать только то, что блокирует следующий этап.
>
> **Обновление 38.1:** Phase 0 readiness + Phase 1 dry smoke выполнены на физической КСО (192.168.110.223).
> 6/6 smoke-кейсов пройдено на Python 3.6.9. Phase 2 (overlay render) НЕ одобрен.

---

## Сейчас (portrait player design завершён — 38.0.6+ implementation)

| # | Действие | Почему |
|---|---|---|
| 1 | **Ничего не менять в коде (пока)** | Не ломать regression baseline |
| 2 | **Поддерживать regression green** | ~3700 тестов — якорь качества |
| 3 | **38.0.6 — Contract & tests ✅** | 71 тест: geometry, forbidden zones, state rules, SLA |
| 4 | **38.0.7 — Shell plan support ✅** | 59 тестов: geometry, visibility, transitions, chromium flags |
| 5 | **38.0.8 — Local kill-switch ✅** | File flag `/run/verny/kso/kill_switch` + shell plan integration, 41 тест |
| 6 | **38.0.9 — State observer stub ✅** | Safe state contract, forbidden fields, 114 тестов |
| 7 | **38.0.10 — Local smoke on dev ✅** | Safe smoke harness, 42 теста |
| 8 | **38.0.11 — Manual test plan ✅** | Physical KSO test plan, 3 phases + stop criteria + rollback |
| 9 | **НЕ менять УКМ5, openbox, Chromium, systemd** | production кассовая система |
| 10 | **38.1 — Physical KSO Phase 0–1 ✅** | Dry smoke 6/6 на Python 3.6.9, Phase 2 ⛔ не одобрен |
| 11 | **38.1.2 — Phase 2 Overlay Attempted ⚠️** | Процесс запущен, xdotool окно НЕ нашёл, visual NOT confirmed |
| 12 | **38.1.4 — Fullscreen Idle Screensaver Design ✅** | Profile contract + interaction hide rules + 141 тест |
| 13 | **38.1.5 — X11 Input Pass-through Design ✅** | Decision matrix (A-E), input_mode contract, +26 тестов |
| 14 | **38.1.6 — X11 Click-through Renderer Contract ✅** | Renderer dataclasses, validators, safe output, 79 тестов |
| 15 | **38.1.7 — X11 Click-through Proof Harness ✅** | 3 режима, command safety, evidence plan, 82 теста |
| 16 | **38.1.8 — Physical X11 Click-through Proof ✅** | SUCCESS. B-FS-1/B-FS-2 closed. HW scanner before pilot. |
| 17 | **38.1.9 — Guarded X11 Screensaver Runner ✅** | State-driven runner, safe output, CLI modes, 124 теста. |
| 18 | **38.1.10 — Physical Run Guarded Runner ✅** | SUCCESS + negative tests (kill-switch, state=payment, rollback). Commit `ad09c49` + `33a8526`. |
| 19 | **38.1.11 — HW Scanner E2E ⚠️** | **INCONCLUSIVE** — scanner not available. Focus-loss defect found. Postponed until scanner arrives. |
| 20 | **38.1.11.1 — Fix Post-Rollback Focus Restore ✅** | `restore_focus()` + focus fields + `focus_warning` stop reason + 14 tests. |
| 21 | **38.2 — Connect X11 Runner to Manifest Creatives ✅** | `screensaver_creative.py`: ScreensaverCreativePayload, adapter, validator, visibility, PoP + 98 tests. |
| 22 | **38.13.3 / D3 — Physical X11 Fullscreen Run ✅** | KSO 192.168.110.223. Profile `portrait_fullscreen_idle_screensaver_768`, window 0x1600001 768×1024+0+0. Visual: 100% green fullscreen. Click-through: focus retained on Chromium. 13/13 stop criteria passed. Rollback clean. D4/D5/D6 NOT executed. |
|| 30 | **38.4 — Control Plane ✅** | Readiness endpoint + portal page + seed helper. 15 backend tests. 4893/4893 green. |
|| 29 | **38.3 — Readiness Gate ✅** | 11-section document, 23 safety tests, 5-phase plan. 4878/4878 green. |
|| 28 | **38.2.7 — Full Dev E2E ✅** | 19 tests: player→JSONL→sidecar classify→payload→backend ingest→report. 4855/4855 green. |
|| 27 | **38.2.6 — Backend Integration E2E ✅** | 32 SQLite in-memory tests, synthetic seed (10 tables), real ingest+list with FK integrity. 4836/4836 green. |
|| 26 | **38.2.5 — Backend Ingest + Portal ✅** | 18 backend service tests, creative_code ingest, idempotency, list filters, safety audit. |
| 25 | **38.2.4 — Dev E2E PoP Validation ✅** | 9-step E2E chain, 31 tests, backend/portal compat, security audit, synthetic data only. |
| 24 | **38.2.3 — PoP Event Queue Bridge ✅** | `screensaver_pop_bridge.py`, ScreensaverPoPDraft→JSONL adapter, creative_code chain, idempotency, +44 tests. |
| 23 | **38.2.2 — Sidecar Media Cache Bridge ✅** | `screensaver_media_availability.py`, media gate in visibility, PoP media_available, SCREENSAVER_EVENT_BLOCKED, +59 tests. |
| 22 | **38.2.1 — Preserve Backend creative_code ✅** | `creative_code` in PlayerPlaylistItem, `is_synthetic` flag, +17 tests. |

---

## Сразу после portrait player design (38.0.5)

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | Реализовать portrait player (новый модуль/профиль) | P0-4, P0-5 | ~5 дней |
| 2 | Интегрировать с sidecar/state-adapter | — | ~2 дня |
| 3 | Протестировать на test KSO (read-only, без перекрытия УКМ5) | — | ~1 день |
| 4 | Закрыть P0-1, P0-2 (device auth) параллельно | P0-1, P0-2 | ~1 день |

**Примечание:** Landscape player сохранён для будущих ландшафтных КСО, не удаляется.
DS API integration — secondary, не блокирует portrait player development.

---

## После успешной test KSO проверки (перед pilot rollout)

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | **Закрыть P0:** device auth на manifest + PoP + persistent session | P0-1, P0-2, P0-3 | ~1 день |
| 2 | RLS на всех query-level путях | P1-2 | ~3 дня |
| 3 | Реальный advertiser/brand/order контекст | P1-3 | ~2 дня |
| 4 | Creative approval lifecycle | P1-4 | ~2 дня |
| 5 | Media delivery через MinIO | P1-5 | ~3 дня |
| 6 | Production device credentials / mTLS | P1-6 | ~3 дня |
| 7 | Замена test-kso врапперов на enterprise | P1-7 | ~5 дней |
| 8 | Portal dashboard + reports backend-driven | P1-8 | ~3 дня |
| 9 | Observability basics (logging, metrics) | P1-9 | ~2 дня |
| 10 | Запуск на 3–5 КСО, 72ч стабильности | — | ~1 неделя |

**Итого на P1:** ~3–4 недели.

---

## После pilot rollout

| # | Действие | Когда |
|---|---|---|
| 1 | Консолидация enterprise + KSO PoP доменов | После pilot |
| 2 | Консолидация manifest/publication доменов | После pilot |
| 3 | Production hardening (TLS, scaling, rate limiting) | После pilot |
| 4 | CI/CD, backup, audit trail | После pilot |
| 5 | Power BI reports, Excel export | По запросу бизнеса |
| 6 | Performance benchmarks, E2E тесты | По мере необходимости |

---

## Что нельзя делать сейчас

| Запрещено | Почему |
|---|---|
| Менять KSO runtime код | Нарушит baseline, заблокирует physical test |
| Добавлять новый функционал | Затянет проект |
| Закрывать P1/P2/P3 долг | Не блокирует physical test |
| Начинать pilot rollout без test KSO | Нет подтверждения на реальном железе |
| Рефакторить архитектуру | Риск дестабилизации |

---

## Файлы

- `docs/audit/technical-debt-next-actions.md` — этот документ

---

## 38.5 — Test-KSO Seed + Publication Readiness (2026-06-25)

### Сделано
- Seed service `POST /api/test-kso/seed` — idempotent synthetic chain
- ReadinessStatus: +15 полей (status, creative_ready, publication, remaining_steps)
- Portal /readiness: 7 групп, все статусы, «Что осталось сделать»
- Backend: 292 теста, Portal: 424 теста — всё зелёное

### Next actions (после 38.5)
- ~~Sidecar config на КСО (field hints уже показаны в readiness)~~ → 38.6: полный checklist
- Media cache readiness на КСО
- Phase D manual approval (остаётся ⛔ blocked)
- `docs/audit/technical-debt-register.md` — полный реестр (36 пунктов)

## 38.5.1 — Sidecar Regression Recheck (2026-06-25)

Sidecar 1838/1838 green за 190.5s. Timeout ложный, не связан с 38.5.
Commit `cf9314d`: DDL fix в тестах (UNIQUE + advertisers/orders).

## 38.6 — Live Config Checklist + Sidecar Config Readiness (2026-06-25)

12 полей sidecar-конфигурации (4 required + 8 optional). Backend: `SidecarConfigField`
модель, `sidecar_config_ready`/`missing_fields`/`checklist`. Portal: таблица полей —
имена visible, значения hidden. Docs: `test-kso-live-config-checklist.md`.

### Next actions (после 38.6)
- ~~Прогнать full regression~~
- ~~Закоммитить~~ → 38.6 done (1f9c56b)
- 38.7: Runbook + operator preflight

## 38.7 — Live Backend Seed Runbook + Operator Preflight (2026-06-25)

Создан `test-kso-live-backend-seed-runbook.md`: Phase A/B/C preflight.
Backend: `required_operator_steps` (12 шагов). Portal: Operator Preflight guidance.
Placeholders без реальных URL/secrets.

### Next actions (после 38.7)
- Full regression + commit ✅
- 38.8: Backend-Only Phase A Live Readiness Check ✅

## 38.8 — Backend-Only Phase A Live Readiness Check (2026-06-26)

Live HTTP: health ✅, seed ✅, readiness ✅, portal ✅.
Исправлен контракт `overall_ready` — теперь честно требует sidecar + media.
Результат: `overall_ready: false`, backend prerequisites зелёные.
Result artifact: `test-kso-phase-a-backend-readiness-result.md`.

### Next actions (после 38.8)
- 38.9: Phase B Sidecar Config Preparation ✅

## 38.9 — Phase B Sidecar Config Preparation (2026-06-26)

Config template `agent_config.json.example`, `.gitignore` protection.
`local_config.validate_no_placeholders()` — dry-check без вывода значений.
`sidecar_config_ready` остаётся `false` (backend не может проверить локальный config).
Doc: `test-kso-sidecar-config-preparation.md`.

### Next actions (после 38.9)
- 38.10: Controlled Phase B preflight ✅

## 38.10 — Controlled Phase B Sidecar Config Application Preflight (2026-06-26)

Preflight doc: `test-kso-sidecar-config-application-preflight.md`:
8-step procedure, safety gates, stop criteria, verification gates, rollback.
Без реальных значений — только placeholders.

### Next actions (после 38.10)
- 38.11: Controlled Phase B final preflight ✅

## 38.11 — Controlled Phase B Final Preflight (2026-06-26)

**Критичная правка безопасности:** замена `echo -n '<SECRET>' | ...` на `read -rsp ...; printf '%s' "$DEVICE_SECRET" | ...; unset DEVICE_SECRET` — секрет не попадает в shell history, `ps aux`, или вывод.

Исправлено в: preflight doc, runbook, preparation doc.

### Next actions (после 38.11)
- ✅ Phase B applied on KSO (2026-06-26, commit `83afb9c`)
- ✅ 38.12: Phase C manifest/media cache preflight
- 38.13: Phase D Manual Approval Gate
- Controlled one-KSO E2E dry run (после approval)

**Phase B deployment details (safe):**
- AGENT_ROOT: `/home/ukm5/kso-agent` on KSO (192.168.110.223)
- device_code: `test-dev-seed`
- 9 subdirectories, agent_config.json (177 bytes), device_secret.dev (Phase B: 32 bytes → Phase C: 25 bytes, 0600)
- Backend reachable: scheme+host verified, no full URL in output
- Secret: present, 600 perms — value never printed

## 38.12 — Phase C Manifest & Media Cache Preflight (2026-06-26)

Preflight doc: `test-kso-phase-c-manifest-media-cache-preflight.md` (13265 bytes).
10-section document: current state, pre-conditions, command templates (masked),
10 safety gates, 10 stop criteria, rollback (partial/full).

### Preflight Status
- ✅ Documented: pre-conditions, command templates, safety gates, stop criteria
- ✅ No network calls from KSO at preflight stage
- ✅ Sidecar/X11/Chromium NOT started
- ✅ Full regression: 4926 green

## 38.12.1 — Phase C Controlled Run + Stabilization (2026-06-25)

### Executed
- ✅ **sync-manifest:** `served` — manifest downloaded (1 item, image/png, slot-000)
- ✅ **sync-media:** `complete` — media downloaded (`slot-000.png`, 108 bytes)
- ✅ **Backend fixes:** ScheduleItem model, device↔display_surface link, schedule_item.date, media_path
- ✅ No secrets/full URLs/tokens in output or committed files

### Next actions (после 38.12.1)
- 38.12.2: Backend regression stabilization (27 errors)
- 38.13: Phase D Preflight + Runbook
- Phase D: физический one-KSO E2E dry run (requires approval)

## 38.12.2 — Backend Regression Stabilization (2026-06-25)

### Executed
- ✅ **27 errors resolved:** PYTHONPATH fix in `backend/pyproject.toml` — added `kso_player` + `kso_sidecar_agent` paths
- ✅ All 292 backend tests green (was 265+27)
- ✅ Portal-web: 404 green (20 BackendIntegration excluded — need live backend)
- ✅ Full regression: 4894 green
- ✅ Secret discrepancy documented: 32→25 bytes = different registration instances

### Next actions (после 38.12.2)
- 38.13: Phase D Preflight + Runbook

## 38.13 — Phase D Preflight (2026-06-25)

### Executed
- ✅ Phase D runbook created: `docs/audit/phase-d-one-kso-e2e-dry-run-preflight.md`
- ✅ 6 sub-phases (D0–D6), 12 stop criteria, rollback, approval gates
- ✅ Readiness verified: backend health, manifest, credential, campaign/placement
- ✅ Regression: 4894 green baseline

### Next actions (после 38.13)
- 38.13.1: Phase D geometry consistency fix (portrait 768×1024)
- Phase D: физический one-KSO E2E dry run (requires explicit manual approval)

## 38.13.1 — Phase D Geometry Consistency Fix (2026-06-25)

### Executed
- ✅ Fixed display_surface: test-dev-seed was 1920×1080 (shared landscape) → now 768×1024 (dedicated portrait)
- ✅ Created portrait logical_carrier + display_surface in DB
- ✅ Created `docs/audit/kso-portrait-architecture-pivot.md`
- ✅ Manifest/media NOT dependent on geometry — no changes needed
- ✅ Full regression: 4894 green

### Next actions (после 38.13.1)
- D2.1: Python 3.6 compatibility fix + fullscreen profile registration
- Phase D: физический one-KSO E2E dry run (requires explicit manual approval)

## D2.1 — Python 3.6 Compatibility + Fullscreen Plan (2026-06-25)

### Executed
- ✅ Created `kso_player/timestamp_utils.py` — `parse_iso_utc()` Python 3.6-compatible parser
- ✅ Replaced all 5 `datetime.fromisoformat()` calls in runtime path
- ✅ Registered `portrait_fullscreen_idle_screensaver_768` profile (768×1024 fullscreen kiosk)
- ✅ 13 timestamp parser tests + existing 130 shell plan/profile tests pass
- ✅ Full regression: pending

### Next actions (после D2.1)
- Phase D3: физический visual run (requires explicit manual approval)

## D3 — Controlled Visual Run (2026-06-25)

### Executed
- ✅ Physical KSO visual run: 768×1024 fullscreen green window, 10s controlled run
- ✅ Click-through confirmed (UKM5 focus preserved)
- ✅ 13/13 stop criteria passed, rollback clean
- ✅ All evidence captured (not in repo)
- ✅ Commit: `b080025`, 6 docs updated

### Next actions (после D3)
- D3.1: Pre-D4 regression triage

## D3.1 — Pre-D4 Regression Triage (2026-06-25)

### Executed
- ✅ Backend: 6 INTERNALERROR fixed (`norecursedirs`), 292 passed
- ✅ Portal-web: 9 BackendIntegration documented (pre-existing)
- ✅ Infra: 1 unittest failure documented
- ✅ Core green: 4917 passed, 0 failures
- ✅ Commit: `dd64ab7`

### Next actions (после D3.1)
- Phase D4: Controlled PoP upload (requires explicit manual approval)

## D4 — Controlled PoP Upload (2026-06-25)

### Executed
- ✅ FK resolution bug discovered and fixed (`8b367eb`: missing Creative/User imports)
- ✅ 1 synthetic PoP event uploaded: HTTP 200, status=accepted
- ✅ PoP count: 0 → 1 (delta +1)
- ✅ Regression baseline updated with FK discovery
- ✅ Commit: `7146029`

### Next actions (после D4)
- Phase D5: PoP report verification (requires explicit manual approval)

## D5 — PoP Report Verification (2026-06-25)

### Executed
- ✅ D4 event visible in backend `/api/proof-of-play/test-kso`
- ✅ All fields verified: campaign=test-camp-seed, creative=test-creative-seed
- ✅ All portal filters pass (device, campaign, creative, placement)
- ✅ Forbidden fields: CLEAN across all report output
- ✅ No new PoP events uploaded, no sidecar/runner/X11 launched

### Next actions (после D5)
- Phase D6: Cleanup (requires separate approval)
- No further actions needed for Phase D one-KSO E2E dry run

## D6 — Cleanup and Phase D Closure (2026-06-25)

### Executed
- ✅ Removed stale test lock dirs (40KB), repo __pycache__, .pytest_cache
- ✅ Preserved: backend PoP event, config/secret/manifest/media cache
- ✅ KSO temp files remain (harmless in /tmp, SSH unreachable)
- ✅ UKM5/Openbox/systemd unchanged
- ✅ No X11/Chromium/runner/sidecar launched

### Phase D complete (D0–D6 all green)
- D0 backend readiness, D1 sidecar status, D2 dry-run, D3 visual run
- D3.1 regression triage, D4 PoP upload, D5 report verify, D6 cleanup
- All constraints met, no secrets committed

### Next recommended actions
- Pilot readiness decision (stakeholder gate)
- HW scanner E2E validation (barcode → campaign match)
- Controlled long-run (hours, not seconds) without auto-start
- BackendIntegration test isolation fix (pre-existing, deferred)

## 38.14 — Pilot Readiness Decision Gate (2026-06-25)

### Decision
- One-KSO technical dry run: **PASSED** (D0–D6 all green)
- One-KSO pilot readiness: **CONDITIONAL** (requires HW scanner E2E + controlled long-run)
- Production/fleet rollout: **NOT APPROVED**

### Documented
- `docs/audit/one-kso-pilot-readiness-decision-gate.md` — полный decision gate
- Proven chain: portal/backend → manifest/media → KSO render → PoP → backend → portal report
- All constraints met, no secrets committed, 4918 regression green

## 38.15 — HW Scanner E2E Validation Plan (2026-06-25)

### Status
- **Validation:** NOT EXECUTED ❌
- **Reason:** physical barcode scanner hardware unavailable
- **Pilot blocker:** 🔴 HIGH — remains active

### Created
- `docs/audit/hw-scanner-e2e-validation-plan.md` — полный validation plan

### Protocol documented
- 4-phase test (S1–S4: pre-scan baseline → launch overlay → scanner test → post-scan verify)
- 8 stop criteria (including: first scan lost, overlay captures input, focus steal, sensitive data)
- 7 absolute safety rules (no barcode logging, no key payload, no UKM5 DB, no payment)
- 6 expected proof points (overlay active, UKM5 focused, input reaches UKM5, no focus steal, no data stored)

### Safe alternatives while scanner blocked
- Controlled long-run plan (38.16)
- BackendIntegration test isolation fix (38.17)
- Pilot runbook update (38.18)

### Not executed
- ❌ No physical scanner test
- ❌ No SSH to KSO
- ❌ No X11/Chromium/runner launch
- ❌ No sidecar daemon
- ❌ No PoP upload
- ❌ No UKM5/Openbox/systemd modification
- ❌ No barcode/key payload logged

## 39.1.1 — Device Gateway Auth Hardening (2026-06-25)

### Status
- **Device gateway auth:** AUTH FOUNDATION DONE ✅
- **PoP ingest:** now requires valid device JWT (was TEST_ONLY)
- **KSO manifest:** now requires valid device JWT (was TEST_ONLY)
- **Media endpoints:** already protected ✅
- **Backend tests:** +13 new auth tests, 305/305 OK

### Hardened endpoints
| Endpoint | Before | After |
|---|---|---|
| `POST /api/device-gateway/kso/{code}/pop` | TEST_ONLY, no auth | JWT device auth + code match |
| `GET /kso/{device_code}/manifest` | TEST_ONLY, no auth | JWT device auth + code match |
| `GET /manifest/current` | Already auth ✅ | No change |
| `GET /media/{id}` | Already auth ✅ | No change |
| `POST /api/device-auth` | Already exists ✅ | No change |

### Deferred (future production hardening)
- mTLS for device identity
- Credential rotation
- Nonce/replay protection
- Rate limiting on device-auth

### Not executed
- ❌ No physical KSO changes / SSH / X11 / Chromium / runner
- ❌ No sidecar daemon / PoP upload
- ❌ No secrets in git or output

### 39.4.1 — Device Dashboard API (2026-06-26)
- ✅ `GET /api/device-dashboard` aggregation endpoint (8 tables cross-referenced)
- ✅ GAP 3: `record_heartbeat()` cross-propagates `last_seen_at` to KsoDevice
- ⏸ GAP 2: sidecar_status in heartbeat deferred to 39.4.4
- ✅ 16 tests green

### 39.4.2 — Portal Device Dashboard Page (2026-06-26)
- ✅ Portal `/device-dashboard` page: 14 columns, summary cards, GET filters, readiness badges
- ✅ 20 portal tests green

### 39.4.3 — Close Device/Sidecar Dashboard Gaps (2026-06-26)
- ✅ GAP 2: `sidecar_status` in heartbeat payload (allowed values: stopped/starting/running/warning/error/unknown)
- ✅ GAP 4: `/readiness` page hardened — uses production `GET /api/device-dashboard` (no test-kso)
- ✅ GAP 5: `/devices` → Device Dashboard CTA link
- ✅ All 7 device/sidecar dashboard GAPs closed
- ✅ Commit: `5557563`

### 40.0 — TZ Alignment / Security & RLS Audit Gate (2026-06-26)
- ✅ Full audit: docs/audit/tz-alignment-security-rls-audit.md (7 разделов)
- ✅ TZ compliance: 27/34 DONE (79%), 4 PARTIAL, 2 MISSING, 1 OUT-OF-SCOPE
- 🔴 Critical: RLS query-level NOT enforced (user_rls_scopes table + UI exist, no WHERE filter)
- 🔴 Pilot blockers: HW scanner E2E (postponed), controlled long-run (decision needed)
- ✅ Recommendation: 40.1 RLS hardening before pilot

### 40.1 — RLS Hardening P0 (2026-06-26)
- ✅ Created `backend/app/domains/identity/rls.py` — RLS enforcement layer
- ✅ Campaigns: advertiser_scope filtering on list + object assertion on code-based get/bind/unbind
- ✅ Creatives: advertiser_scope filtering on list + object assertion on get/create/upload
- ✅ Approvals: multi-type advertiser resolution (campaign/placement/batch), scope on list/get/request/decide
- ✅ Reports/PoP: advertiser_scope join through campaign_code, scope on /reports/pop + /summary
- ✅ Device dashboard: device_code scope + store scope post-filter
- ✅ Test-KSO readiness: now requires authentication (was unauthenticated)
- ✅ 17 new RLS unit tests: scope context, query filter, object assertion, admin bypass
- ✅ Backend regression: 398 → 415 (+17 RLS tests), all green

### 40.1.1 — RLS Endpoint Integration Verification & P0 Patch (2026-06-26)
- 🔴 P0 FIXED: `patch_campaign_by_code` — added advertiser scope assertion (was unprotected)
- 🔴 P0 FIXED: `archive_campaign_by_code` — added advertiser scope assertion (was unprotected)
- 🔴 P0 FIXED: `list_campaign_creatives` — added advertiser scope assertion (was unprotected)
- 🔴 P0 FIXED: `unbind_campaign_creative` — added advertiser scope assertion (was unprotected)
- 🔴 P0 FIXED: Placements `list/get/create` — advertiser scope via campaign_code resolution
- 🟡 DEFERRED: Schedule/ScheduleSlot query-level RLS join optimization (router-level scope check feasible, query-level join for lists deferred)
- 🟡 DEFERRED: Manifests/publications RLS — not directly linked to advertiser, scope via campaign chain deferred
- ✅ All remaining campaign code-based endpoints now RLS-gated: get, patch, archive, bind, unbind, list_creatives
- ✅ Placements now RLS-gated: list (post-filter), get (assert), create (assert)
- ✅ Backend regression: 415 green, no regressions from RLS patches

### 40.1.2 — RLS Endpoint Evidence & Gate Closure (2026-06-26)
- ✅ Schedules RLS: `_resolve_schedule_advertiser()` → all 11 endpoints scoped
- ✅ Placements: PATCH + archive scope check added
- ✅ Publications: `_resolve_batch_advertiser()` → all 12 endpoints scoped
- ✅ Manifests: `_resolve_manifest_advertiser()` → all 8 endpoints scoped
- ✅ 42 endpoint-level tests in `test_rls_endpoint_enforcement.py`
- ✅ Backend: 457 green; total 5116

### 40.1.3 — Regression Baseline Cleanup (2026-06-26)
- ✅ Portal BackendIntegration tests separated (`skipUnless` with `RUN_PORTAL_BACKEND_INTEGRATION=1`)
- ✅ Sidecar non-deterministic test fixed (`test_client_repr_safe`)
- ✅ All 6 suites green: **5106 passed, 32 skipped, 0 failed**
- ✅ RLS gate closed, commits `67baca7` + `1b51894`

## 40.2 — Admin Audit Hardening (2026-06-26)

### Status
- ✅ Centralized `audit_business_action()` with automatic forbidden-field stripping
- ✅ Campaigns: create, update, archive, bind_creative, unbind_creative
- ✅ Creatives: create, update, upload_version
- ✅ Approvals: request, approve
- ✅ Publications: create, request_approval, approve, generate_manifests, publish, cancel
- ✅ Manifests: generate, publish
- ✅ Identity (existing): create_user, block_user, archive_user, unblock_user, update_roles, update_rls_scopes
- ✅ Device gateway (existing): manifest delivery audit
- ✅ Audit endpoint enhanced: filters for action, target_type, target_ref, actor_id
- ✅ Portal `/admin` page shows audit events (pre-existing, RBAC-guarded)
- ✅ Payload redaction: strips passwords, secrets, tokens, backend URLs, barcodes, PII
- ✅ 18 tests in `test_audit_hardening.py`
- ✅ Regression: 5124 passed, 32 skipped, 0 failed
- ✅ Commit: `8ff648a`

### Deferred
- Failed/security events (forbidden RLS, failed maker-checker) — requires middleware rewrite
- Device credential create/revoke audit — already exists in device gateway

## 40.3 — Pilot Readiness Gates Plan (2026-06-26)

### Status
- ✅ `docs/audit/pilot-readiness-gates-plan.md` created — comprehensive gates document
- ✅ Gate A (HW scanner E2E): protocol documented, approval token defined, STOPPED (no scanner)
- ✅ Gate B (Controlled long-run): 1h/8h/48h options, monitoring plan, success/fail criteria
- ✅ Gate C (Pilot runbook): structure defined (10 sections), content after Gates A/B
- ✅ Gate D (Go/No-Go): 11 criteria matrix, decision logic
- ✅ Approval tokens: 7 tokens defined, lifecycle rules
- ✅ Current verdict: **NO-GO** (scanner + long-run not done)
- ❌ No physical actions executed
- ❌ No KSO/SSH/X11/Chromium/runner/sidecar/PoP launched

### Next
- 40.3.1: HW scanner E2E — BLOCKED (no scanner hardware)
- 40.3.2: Controlled 1h technical soak — ready, needs approval token
- 40.3.3: Pilot runbook finalization — after Gates A/B
- 40.4: v0.11.0 release tag — after gates green
