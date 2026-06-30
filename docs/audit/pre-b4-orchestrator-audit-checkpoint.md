# Pre-B.4 Channel Orchestrator — Architecture & Regression Audit

**Date:** 2026-06-29
**HEAD:** `3c5bbd2` (B.3.5 Closure Gate)
**Git:** clean ✅ | **GitHub:** pushed ✅

---

## Executive Summary

Проект готов к B.4.0 Channel Orchestrator Design Gate. B.3 Placement закрыт без новых regression failures. Все 9 обязательных документов на месте. Архитектура чистая: orchestrator/ и adapters/ — пустые скелеты (только `__init__.py`). Publication flow, campaign submit, generated_manifests FK, kso_placements, campaign_targets — не менялись в B.3. Placement DB целостность: 0 NULL, 0 orphans. RLS enforced (7 точек), audit consistent (4 действия, placement_code). Backend: 947/881/66/0. Portal: 803/0.

**Рекомендация: GO для B.4.0 Design Gate.**

---

## Git Baseline

| Параметр | Значение |
|---|---|
| HEAD | `3c5bbd2` |
| Branch | `main` |
| Status | clean |
| Remote | `github.com:santanas-dev/retail-media-platform` |
| Last push | `f233760..3c5bbd2` |

**B.3 commits (7):** `aada294` → `460f23b` → `ce8c439` → `3ff11ca` → `8676c59` → `de763c7` → `f233760`

---

## B.3 Closure Verification

| Check | Result |
|---|---|
| B.3 marked COMPLETED in roadmap | ✅ |
| Next step = B.4 | ✅ |
| Baseline format: collected/passed/pre-existing/errors | ✅ |
| "882/0" replaced with proper format | ✅ (only in historical docs) |

---

## Documentation Consistency

| Document | Status |
|---|---|
| `tz-v2-5-realignment-roadmap-46-1.md` | ✅ B.3 = COMPLETED |
| `current-project-state-after-b3.md` | ✅ |
| `b3-placement-closure.md` | ✅ |
| `b3-placement-design-gate.md` | ✅ |
| `b3-3-placement-functional-validation.md` | ✅ |
| `b3-3-1-regression-delta-real-api-validation.md` | ✅ |
| `b3-4-placement-portal-readonly.md` | ✅ |
| `b2-2-qa-pipeline-baseline.md` | ✅ |
| `erd-v2-5-a2.md` | ✅ |

---

## Architecture State Before B.4

### Domain inventory (21 domains)

| Domain | State | Notes |
|---|---|---|
| `campaigns` | Active | Campaign 1→N Placement, submit validation intact |
| `channels` | Active | Placement + PlacementTarget ORM, 7 API endpoints |
| `publications` | Active | **Publication flow untouched** in B.3 |
| `manifests` | Active | `generated_manifests` table, FK → kso_placements |
| `orchestrator` | **Empty** | Only `__init__.py` — skeleton not started |
| `adapters` | **Empty** | Only `__init__.py` — no adapter code |
| `scheduling` | Active | `kso_placements` table (legacy) |
| `proof_of_play` | Active | FK → `generated_manifests`, FK → `kso_placements` |
| `device_gateway` | Active | Not touched in B.3 |
| `test_kso_readiness` | Active | Seed references kso_placements |

### Key findings

1. **orchestrator/** и **adapters/** — пустые скелеты. Это правильное состояние: B.4 должен их наполнить.
2. **Publication flow** — в `publications/router.py` + `publications/service.py`. Не менялся в B.3.
3. **Manifest generation** — в `manifests/router.py` + `manifests/service.py`. B.4 Orchestrator должен вызывать manifests, а не заменять.
4. **kso_placements** — legacy таблица в scheduling, FK-связана с generated_manifests + proof_of_play. Не менять.
5. **generated_manifests** — FK от proof_of_play. Не менять.
6. **B.4 должен встроиться** между campaigns/placements и manifests/publications, не меняя ни один из них.

---

## Placement Readiness for Orchestrator

| Check | Result |
|---|---|
| `placements.channel_id` NOT NULL | 0 NULLs ✅ |
| Placement ORM | Exists ✅ |
| PlacementTarget ORM | Exists ✅ |
| Campaign.placements relationship | Exists ✅ |
| Placement service/API | 12 functions + 7 endpoints ✅ |
| Targets linked to display_surfaces | 1/1 ✅ |
| Audit target_ref = placement_code | 4/4 ✅ |
| Portal read-only | No CRUD ✅ |
| Orphan placement_targets | 0 ✅ |
| campaign_targets preserved | ✅ |
| kso_placements preserved | ✅ |

---

## Publication/Manifest Safety

| Check | Result |
|---|---|
| Publication flow changed in B.3 | **No changes** ✅ |
| generated_manifests FK changed | **No changes** ✅ |
| kso_placements deleted | **No** ✅ |
| Campaign submit validation changed | **No changes** (0 diff lines) ✅ |

**B.4 constraint:** B.4 не должен менять publication flow, generated_manifests FK, campaign submit, kso_placements без отдельного design gate.

---

## Security/RLS/Audit Readiness

| Check | Result |
|---|---|
| RLS enforcement points in placement service | 7 ✅ |
| Cross-advertiser tests | 5 ✅ |
| Audit action: placement.create | ✅ placement_code |
| Audit action: placement.update | ✅ placement_code |
| Audit action: placement.cancel | ✅ placement_code |
| Audit action: placement.targets.update | ✅ placement_code |
| Portal CRUD bypass | 0 forms/buttons ✅ |

**B.4 constraint:** B.4 не должен ослаблять RBAC/RLS. Orchestrator должен наследовать advertiser scope от Placement→Campaign.

---

## Test Baseline

### Backend
| Метрика | Значение |
|---|---|
| Collected | **947** |
| Passed | **881** |
| Failed | **66** (all pre-existing) |
| Collection errors | **0** |
| B.1+B.2 | 38/38 |
| Core | 73/73 |
| B.3 total | 65/65 |

### Portal
| Метрика | Значение |
|---|---|
| Passed | **803** |
| Failed | **0** |
| Skipped | 20 |

---

## Risks Before B.4

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Orchestrator меняет publication flow | HIGH | B.4.0 Design Gate: чёткая граница Orchestrator ↔ Publications |
| 2 | Manifest преждевременно пишет в generated_manifests | HIGH | B.4.0: Orchestrator вызывает существующий manifest service, не заменяет |
| 3 | Adapter layer смешивается с Device Gateway | MEDIUM | Разделение доменов: orchestrator/adapters ≠ device_gateway |
| 4 | KSO legacy становится основной моделью | MEDIUM | Campaign→Placement универсальны; KSO — один из каналов |
| 5 | Simulation становится real publish | MEDIUM | Dry-run флаг обязателен в B.4.0 design |
| 6 | RLS забыта при simulation | HIGH | Orchestrator наследует advertiser scope |
| 7 | Audit не покрывает orchestrator actions | MEDIUM | Добавить audit в B.4.0 design |

---

## What B.4 Must Not Touch

- ❌ `campaign_targets` — не удалять, не менять FK
- ❌ `kso_placements` — не удалять, не менять FK
- ❌ `generated_manifests` FK — не менять
- ❌ Publication flow (`publications/`) — не менять
- ❌ Campaign submit validation — не менять
- ❌ Placement API (7 endpoints) — не менять
- ❌ RBAC/RLS — не ослаблять
- ❌ Legacy KSO tables — не трогать
- ❌ Device Gateway — не начинать
- ❌ DROP/TRUNCATE — запрещены

---

## GO/NO-GO for B.4.0 Design Gate

**✅ GO — B.4.0 Channel Orchestrator Design Gate**

Условия выполнены:
- B.3 закрыт, 0 новых failures
- Архитектура чистая: orchestrator/adapters — пустые скелеты
- Publication flow + manifests не менялись
- Placement готов: DB, ORM, API, RLS, audit
- Все запрещённые артефакты сохранены

---

## Recommended Next Prompt

```
Задача: выполнить B.4.0 — Channel Orchestrator Design Gate.
Создать design-документ (без кода):
- Границы Orchestrator: что делает, что НЕ делает
- AdapterContract интерфейс
- Как Orchestrator вызывает существующие manifests/publications
- Как simulation отличается от real publish
- Как RLS наследуется через Placement→Campaign
- Какие audit events нужны
- Mock adapter для тестов
Не писать код. Не трогать publication flow, manifests, campaign submit.
```
