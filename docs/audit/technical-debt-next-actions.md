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
- Full regression + commit
- 38.8: Phase D Manual Approval Gate
