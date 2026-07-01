# G.0 — Phase G Roadmap Sync / Pre-Audit / Design Gate

**Status:** COMPLETED (Design Gate)  
**Date:** 2026-07-10  
**Commit:** (see report)

---

## Executive Summary

Phase G в roadmap — **Emergency & Operations (P2)**. Три цели: Emergency Management (G.1), Operational Health Center (G.2), Staged Rollout (G.3). G.3 (production switch) конфликтует с существующими NO-GO — рекомендован deferred design gate. Предложен safe split: G.1 schemas/contracts → G.2 service → G.3 API → G.4 portal → G.5 security gate → G.6 closure. Без KSO production switch. Без ClickHouse.

---

## 1. Current State After Phase F

### Что есть (фазы A–F)

| Слой | Статус |
|---|---|
| Multichannel core (channel/device/placement/orchestrator) | ✅ |
| Device Gateway (auth, manifest delivery, PoP ingestion) | ✅ |
| Universal Manifest v1 | ✅ |
| KSO Adapter (preview, dry-run) | ✅ |
| Inventory & Planning (read-only) | ✅ |
| Analytics: normalization, aggregation, API, portal | ✅ |
| RLS/Scope enforcement | ✅ |
| Audit | ✅ |

### Что deferred

| Item | Фаза |
|---|---|
| ClickHouse pipeline | F (deferred) |
| Placement/store JOIN в normalizers | F (deferred) |
| expected_impressions из planning | F (deferred) |
| Export reports | F (deferred) |
| KSO production switch | E/F (deferred) |
| Compatibility projection | E (deferred) |
| Signed manifests | H (future) |
| HA / backups / monitoring | H (future) |

### Test baselines

| Слой | Результат |
|---|---|
| Backend collection | 2145 / 0 errors |
| Analytics suite (F.1–F.4.1) | 268/268 |
| Phase E targeted | 217/217 |
| Planning + Inventory | 254/254 |
| Portal full | 974 collected / 934 passed / 32 skipped / 8 pre-existing |

---

## 2. Roadmap Phase G Reading

Из `tz-v2-5-realignment-roadmap-46-1.md`:

> **Фаза G: Emergency & Operations (P2)**
> - G.1 — Emergency Management: стоп-реклама, экстренное сообщение, возврат. Уровни: устройство/магазин/кластер/филиал/сеть. Аудит и прогресс доставки.
> - G.2 — Operational Health Center: дашборд здоровья устройств, детализация до магазина/устройства, алерты по критичным событиям.
> - G.3 — Staged Rollout: лаборатория → 5 магазинов → ... → вся сеть, авто-стоп при превышении порога ошибок, rollback.
>
> **Blockers:** нужен Device Gateway + PoP  
> **KSO hardware:** желательно  
> **Priority:** P2  
> **Оценка:** 2–4 сессии, Medium сложность

### Интерпретация

G.1 и G.2 — это **операционные возможности**, не связанные напрямую с рекламным контентом. G.3 — это **production rollout** с авто-стопом и rollback.

G.3 затрагивает производственный контур KSO, что прямо конфликтует с существующими NO-GO:
- NO-GO для KSO production switch без отдельного design gate
- NO-GO для real publish switch без отдельного design gate

---

## 3. Candidate Phase G Scopes

### A. Emergency Management + Health Center (safe)

**Scope:** G.1 + G.2, без G.3  
**Что даёт:** стоп-реклама, экстренные сообщения, дашборд здоровья  
**Риски:** требует новых моделей/API, но без production switch — безопасно  
**Без KSO hardware:** да, можно на mock-данных  

### B. Full Emergency + Ops + Rollout Design Gate (extended)

**Scope:** G.1 + G.2 + G.3 design-only  
**Что даёт:** полный design gate для всех трёх этапов, но без реализации rollout  
**Риски:** G.3 design может устареть до момента production readiness  
**Без KSO hardware:** да, design-only  

### C. Production Readiness Continuation (skip G, go to H)

**Scope:** перейти сразу к H (HA, backups, monitoring, load testing)  
**Что даёт:** инфраструктурная готовность к пилоту  
**Риски:** нет операционных инструментов (стоп-реклама) для пилота  

---

## 4. Recommended Phase G Scope

**Рекомендация: Candidate A — Emergency Management + Health Center (G.1 + G.2), G.3 deferred как отдельный design gate.**

### Причины

1. **G.1 (Emergency Management)** — критично для любого пилота. Без возможности экстренно остановить рекламу пилот рискован.
2. **G.2 (Health Center)** — частично уже есть фундамент (device_health endpoint F.4). Можно расширить.
3. **G.3 (Staged Rollout)** — требует production switch, что конфликтует с NO-GO. Deferred.

### Recommended split

| Step | Что | Тип |
|---|---|---|
| **G.0** | Roadmap Sync / Pre-Audit / Design Gate | ✅ этот документ |
| **G.1** | Emergency Management: schemas/contracts | Design + schemas |
| **G.2** | Emergency Management: service implementation | Read-only service |
| **G.3** | Emergency Management API + Health Center API | Read-only API |
| **G.4** | Portal: emergency dashboard + health dashboard | Read-only portal |
| **G.5** | Security / RLS / Regression Gate | Verification |
| **G.6** | Phase G Closure Gate | Documentation |

**Все read-only до явного production switch gate.**

---

## 5. Explicit NO-GO Items

Действуют все предыдущие NO-GO:

| NO-GO | Обоснование |
|---|---|
| ❌ ClickHouse implementation | Требует отдельного performance gate |
| ❌ KSO production switch | Требует отдельного design gate + approval |
| ❌ Real publish switch | Требует compatibility projection gate |
| ❌ UniversalManifest → GeneratedManifest write | Требует compatibility projection gate |
| ❌ DROP/DELETE/TRUNCATE | Безвозвратная потеря данных |
| ❌ Миграции без design review | Risk of breaking production schema |
| ❌ Portal CRUD без backend authorization | RLS bypass risk |
| ❌ JS/CDN/localStorage в portal | Security contract |

**Дополнительно для G:**
| NO-GO | Обоснование |
|---|---|
| ❌ Автоматический стоп-реклама без audit trail | Требуется полный audit каждой остановки |
| ❌ Экстренное сообщение с HTML/JS инъекцией | Только plain text |
| ❌ Staged rollout без approval gate | Production switch |

---

## 6. Deferred Items From Previous Phases

| Item | Current phase | Рекомендация для G |
|---|---|---|
| ClickHouse pipeline | F | Не в scope G |
| Placement/store JOIN | F | Не в scope G |
| expected_impressions | F | Не в scope G |
| Export reports | F | Не в scope G |
| KSO production switch | E/F | Deferred design gate |
| Compatibility projection | E | Deferred |
| Signed manifests | Future (H) | Не в scope G |
| HA / backups / monitoring | Future (H) | Не в scope G |

---

## 7. Risks and Blockers

| Risk | Severity | Mitigation |
|---|---|---|
| G.3 production switch преждевременен | High | Deferred до отдельного gate |
| 47 pre-existing backend failures | Medium | Не блокируют G.1/G.2 (read-only) |
| 8 pre-existing portal live-integration errors | Low | Требуют running backend — не блокируют |
| placement/store unknown в analytics | Low | Не влияет на Emergency/Health |
| Нет signed manifests | Low | Не влияет на Emergency/Health |
| KSO player compatibility не тестировалась | Medium | Блокирует G.3, но не G.1/G.2 |

---

## 8. Security / RLS / Audit Guardrails

Для Phase G:
- Emergency actions (стоп-реклама) — только `campaigns.manage` / `emergency.manage`
- Health dashboard — `reports.read` или `devices.gateway.read`
- Все audit события — `emergency.*.triggered`, `health.*.viewed`
- No secrets в audit
- RLS: стоп-реклама только для своих кампаний
- No device credentials exposure
- No advertiser/store leakage

---

## 9. Data / Migration Decision

**G.1:** Может потребоваться таблица `emergency_actions` (стоп-реклама, сообщение, статус доставки). Миграция будет рассмотрена в G.1 sub-design.

**G.2:** Основан на существующих данных (device_health endpoint F.4, device_gateway models). Миграции не требуются для read-only dashboard.

**Решение:** G.1 schemas/contracts phase решит вопрос миграций. В G.0 миграции не создаются.

---

## 10. API Decision

**G.0:** API не создаётся.

**G.1:** Schemas/contracts только. API — в G.3.

**G.2:** Service только. API — в G.3.

**G.3:** Read-only API для health dashboard + controlled internal API для emergency management (campaigns.manage permission).

---

## 11. Portal Decision

**G.0:** Portal не меняется.

**G.4:** Read-only portal pages для emergency status + health dashboard.

---

## 12. ClickHouse Decision

**ClickHouse не в scope G.** Не требуется для emergency management или health dashboard на текущих объёмах.

---

## 13. KSO Production Switch Decision

**NO-GO для G.** G.3 (Staged Rollout) deferred как отдельный design gate. Требуется:
- Compatibility projection gate
- KSO player compatibility test
- Approval before switch

---

## 14. Test Baseline (G.0)

| Слой | Результат |
|---|---|
| Backend collection | 2145 / 0 errors |
| Analytics suite | 268/268 |
| Phase E targeted | 217/217 |
| Planning + Inventory | 254/254 |
| Portal full | 974 collected / 934 passed / 32 skipped / 8 pre-existing |

---

## 15. GO / NO-GO

**✅ GO для G.1 — Emergency Management: schemas/contracts**

Условия:
- Design-only: schemas, contracts, validation helpers
- Без миграций (решение в G.1 sub-design)
- Без API
- Без portal
- Без ClickHouse
- Без KSO production switch
- Без изменения существующих моделей

**NO-GO для G.3 (Staged Rollout) implementation — deferred design gate.**
**NO-GO для прямого включения ClickHouse.**
**NO-GO для KSO production switch.**
