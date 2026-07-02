# PILOT.0 — Pilot GO Action Plan / Evidence Tracker

**Date:** 2026-07-01 | **Phase:** PILOT.0 | **Type:** Docs-only

---

## Что создано

| # | Документ | Назначение |
|---|---|---|
| 1 | `docs/operations/pilot-go-action-plan.md` | План выполнения 6 blockers: порядок, зависимости, acceptance criteria, timeline |
| 2 | `docs/operations/pilot-go-evidence-tracker.md` | Evidence tracker: 50+ checkpoints, per-blocker status, reviewer, decision |
| 3 | `docs/operations/templates/support-escalation-path-template.md` | L1/L2/L3 escalation path template — закрывает P13 |

---

## Какие blockers покрыты планом

| # | Blocker | Action Plan | Evidence Tracker |
|---|---|---|---|
| B1 | Pilot store/device list | 7 шагов, 1 час | 7 checkpoints |
| B2 | Monitoring deployment | 12 шагов, 1 день | 12 checkpoints |
| B3 | Backup/restore drill | 11 шагов, 2 часа | 11 checkpoints |
| B4 | KSO physical playback test | 10 шагов (9 фаз), 4 часа | 10 checkpoints |
| B5 | Security approval | 7 шагов, 1 день | 7 checkpoints |
| B6 | Business approval | 8 шагов, 1 день | 8 checkpoints |
| P13 | Support escalation path | ✅ Template created | Закрыт |

---

## Статус 6 blockers после PILOT.0

| # | Blocker | Статус | Что изменилось |
|---|---|---|---|
| B1 | Pilot list | 🟡 Template + action plan | +7-step execution plan |
| B2 | Monitoring | 🟡 Configs + action plan | +12-step deployment plan |
| B3 | Backup drill | 🟡 Protocol + action plan | +11-step drill plan |
| B4 | KSO test | 🟡 Protocol + action plan | +10-step test plan |
| B5 | Security approval | 🟡 Template + action plan | +7-step approval process |
| B6 | Business approval | 🟡 Template + action plan | +8-step approval process |
| P13 | Support escalation | 🟡 Template (was ❌) | NEW: L1/L2/L3 template |

**Все 6 blockers остаются 🟡 PARTIAL — evidence НЕТ, approvals НЕТ. PILOT.0 дал roadmap, не решение.**

---

## Pilot readiness после PILOT.0

| Статус | Количество |
|---|---|
| ✅ READY | **7** |
| 🟡 PARTIAL (templates/protocols/plans ready) | **9** |
| ❌ Missing | **0** |

**0 критериев полностью MISSING. Все имеют templates, protocols, или action plans. Но реальный pilot — NO-GO без evidence.**

---

## Что разрешено дальше

- ✅ Execute B2 (deploy monitoring) — lab environment
- ✅ Execute B3 (backup/restore drill) — lab/stage DB only
- ✅ Execute B4 (KSO physical test) — lab only, no prod switch
- ✅ Fill B1 (pilot list) — after B4 confirms working device
- ✅ Obtain B5 (security approval) — after B2, B3, B4 evidence
- ✅ Obtain B6 (business approval) — after B1, B5

## Что запрещено

- 🚫 Production switch
- 🚫 Real pilot in stores
- 🚫 Real emergency execution
- 🚫 ClickHouse / KSO prod switch / mTLS
- 🚫 Any backend/portal/Docker/.env changes

---

## Подтверждение docs-only

- ✅ 0 backend code changes
- ✅ 0 portal code changes
- ✅ 0 migrations
- ✅ 0 DB schema changes
- ✅ 0 Docker/.env changes
- ✅ 0 active docker-compose changes
- ✅ 0 secrets in templates
- ✅ All templates use `<PLACEHOLDER>` / `____` notation

---

## GO / NO-GO

| Gate | Decision |
|---|---|
| **PILOT.0 — action plan + evidence tracker** | ✅ **DONE** |
| **Execute 6 pilot actions** | 🟢 **GO** — follow `pilot-go-action-plan.md` |
| **Real pilot** | 🚫 **NO-GO** — until evidence collected |
| **Production switch** | 🚫 **NO-GO** |
