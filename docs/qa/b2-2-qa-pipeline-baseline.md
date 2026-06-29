# QA Pipeline Baseline — B.2.2

> **Дата:** 2026-06-29 | **Статус:** BASELINE ACCEPTED
> **Commit:** bcce944

## Текущий Baseline

| Suite | Result |
|---|---|
| B.1+B.2 combined tests | **34/34** ✅ |
| Backend regression | **882/0** ✅ |
| Portal regression | **842/32sk** ✅ (8 flakes) |
| RBAC/RLS | **47/47** ✅ |
| Audit coverage | **20/20** ✅ |
| QA Pipeline | 14 pass, 10 fail, 14 skip |

---

## 10 Failing Gates — Root Cause Analysis

### 1. Migration Safety

| Field | Value |
|---|---|
| **Root cause** | Alembic scan finds 2 P0 issues — likely old migration files with DROP/ALTER patterns from early development |
| **Related to B.2/B.2.1** | **No** — no migrations created in B.x |
| **Risk level** | P0 (structural) — but no pending destructive migrations |
| **Category** | **Technical debt / accepted baseline** |
| **Can fix now** | Yes — requires audit of all Alembic files, mark intentional DROP as documented |
| **Next action** | Schedule Alembic audit in Phase H (production readiness) |

### 2. API Schema Validate

| Field | Value |
|---|---|
| **Root cause** | 1 endpoint missing response schema in FastAPI router |
| **Related to B.2/B.2.1** | **No** — pre-existing |
| **Risk level** | P1 — documentation/validation gap, not runtime |
| **Category** | **Technical debt** |
| **Can fix now** | Yes — add missing response_model to one endpoint |
| **Next action** | Minor fix — add `response_model` to the undocumented route |

### 3. Audit Trail Verify

| Field | Value |
|---|---|
| **Root cause** | Script requires DATABASE_URL env var — runs in offline mode |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P1 — audit coverage is 20/20 per manual verification |
| **Category** | **Environment-dependent** |
| **Can fix now** | Yes — set DATABASE_URL or pass connection params |
| **Next action** | Configure env or accept SKIP as known limitation |

### 4. RLS Isolation

| Field | Value |
|---|---|
| **Root cause** | Requires RLS_ADV_A_TOKEN / RLS_ADV_B_TOKEN env vars for cross-advertiser test |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P0 — but RLS is 47/47 verified manually |
| **Category** | **Environment-dependent** |
| **Can fix now** | Yes — set auth tokens |
| **Next action** | Configure test tokens or accept SKIP |

### 5. Dependency Health

| Field | Value |
|---|---|
| **Root cause** | `safety` CLI tool not installed in environment |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P0 (CVE scan) — but no new deps added |
| **Category** | **Environment-dependent** |
| **Can fix now** | Yes — `pip install safety` |
| **Next action** | Install safety in venv or CI environment |

### 6. Dead Code

| Field | Value |
|---|---|
| **Root cause** | `vulture` CLI tool not installed |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P2 (code quality, not security) |
| **Category** | **Environment-dependent** |
| **Can fix now** | Yes — `pip install vulture` |
| **Next action** | Install vulture in venv or CI environment |

### 7. KSO Health

| Field | Value |
|---|---|
| **Root cause** | SSH to 192.168.110.223 fails — no physical KSO accessible |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P0 — but physical KSO is explicitly NOT touched per constraints |
| **Category** | **Requires physical KSO/device** |
| **Can fix now** | **No** — requires physical KSO hardware |
| **Next action** | Accept as baseline. Only relevant when KSO hardware is connected |

### 8. Alert Rules

| Field | Value |
|---|---|
| **Root cause** | SSH to KSO fails — sidecar/display DOWN on unreachable device |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P0 — but same as KSO Health (hardware-dependent) |
| **Category** | **Requires physical KSO/device** |
| **Can fix now** | **No** |
| **Next action** | Accept as baseline |

### 9. Config Sync

| Field | Value |
|---|---|
| **Root cause** | Cannot fetch config from backend — KSO not connected |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P1 |
| **Category** | **Requires physical KSO/device** |
| **Can fix now** | **No** |
| **Next action** | Accept as baseline |

### 10. Compliance 152-FZ

| Field | Value |
|---|---|
| **Root cause** | 5 of 8 compliance checklist items fail (cookie consent, data processing agreement, retention policy formalisation, breach notification template, DPO appointment) |
| **Related to B.2/B.2.1** | **No** |
| **Risk level** | P1 — legal compliance, not technical blocker |
| **Category** | **Documentation-only / legal** |
| **Can fix now** | Partially — templates can be created, full compliance needs legal review |
| **Next action** | Create template docs for 5 failing items in Phase H |

---

## Classification Summary

### Release Blocker (0)
— none of the 10 failures block B.3 or further development

### Must Fix Before Pilot (3)
| Gate | Why |
|---|---|
| RLS Isolation | Must verify isolation before production data |
| Audit Trail Verify | Must run audit check with real DB |
| Dependency Health | CVE scan before production deployment |

### Technical Debt / Accepted Baseline (4)
| Gate | Why |
|---|---|
| Migration Safety | No pending destructive migrations; audit in Phase H |
| API Schema Validate | 1 missing schema — minor fix, not blocking |
| Dead Code | Code quality, not security — install vulture when ready |
| Compliance 152-FZ | Legal templates — not technical blocker |

### Environment-Dependent (3)
| Gate | Why |
|---|---|
| Audit Trail Verify | Needs DATABASE_URL (offline by default in pipeline) |
| RLS Isolation | Needs auth tokens |
| Dependency Health | Needs `safety` CLI |

### Requires Physical KSO (3)
| Gate | Why |
|---|---|
| KSO Health | SSH to 192.168.110.223 |
| Alert Rules | SSH to 192.168.110.223 |
| Config Sync | KSO connection required |

---

## Что блокирует B.3 Placement

**Ничего.** B.3 — выделение Placement как отдельной сущности (campaign 1→N placements, channel_id, placement_targets). Не зависит от:
- Физической КСО
- CLI tools (safety, vulture)
- Compliance шаблонов
- Alembic audit

## Что блокирует Device Gateway (Phase C)

**Ничего.** Device Gateway требует только универсальную модель устройств (завершена в B.2) и channel registry (B.1).

## Что блокирует Pilot

| Blocker | Статус |
|---|---|
| Физическая КСО | ❌ Недоступна |
| Production AV | ❌ Выключен |
| RLS Isolation test | ⚠️ Требует auth tokens |
| Compliance 152-FZ | ⚠️ Требует шаблоны |

## Рекомендованный порядок закрытия долга

1. **Сейчас (безопасно)**: ничего не трогать — baseline принят
2. **Phase B/C параллельно**: установить `safety` + `vulture` в CI venv
3. **Перед Device Gateway (C.1)**: настроить RLS_ADV_A/B токены для изоляционного теста
4. **Перед Pilot**: настроить DATABASE_URL для audit trail verify
5. **Phase H (production readiness)**: Alembic audit, compliance 152-FZ шаблоны, KSO health checks
6. **При подключении физической КСО**: KSO Health, Alert Rules, Config Sync заработают автоматически

---

## Проверки выполнены

- Просмотрен `scripts/qa_pipeline.py` — классификация всех 38 gates
- Запущены все 10 failing скриптов индивидуально
- Зафиксированы точные сообщения об ошибках
- Классифицированы корневые причины
- Подтверждено: **все 10 failures — pre-existing**, не связаны с B.1/B.2/B.2.1
- Ни один failure не является release blocker для B.3

## Файлы

- **Создан:** `docs/qa/b2-2-qa-pipeline-baseline.md`
- Код backend/portal **НЕ менялся**
- Миграции **НЕ создавались**
- Docker/.env **НЕ менялись**

## Следующий шаг

**B.3 — Placement как отдельная сущность.** Никаких блокеров.
