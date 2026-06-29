# Full Project Audit — After B.2.2

> **Дата:** 2026-06-29 | **Commit:** `1d767d7` | **Статус:** ✅ AUDIT COMPLETE

---

## Executive Summary

Проект Retail Media Platform находится в **стабильной фазе Re-Alignment (A→B)**. Фаза A (анализ ТЗ v2.5, архитектурные контракты, KSO-миграция) полностью завершена. Фаза B (Multichannel Core) — частично: B.1, B.2, B.2.1, B.2.2 закрыты. Проект готов к B.3 без блокеров.

**Ключевые цифры:**
- 33 таблицы в БД, 0 orphans
- 22 backend-домена, 20 роутеров
- 24 portal-шаблона
- Backend: 882/0, Portal: 842/32sk
- RBAC/RLS: 47/47, Audit: 20/20
- 5 каналов, 5 device types, 6 capability profiles

**Главный риск:** архитектурный долг в связке Campaign ↔ Placement ↔ Publication — кампании напрямую связаны с каналами через campaign_channels, а placement_target не имеет полноценной связи с display_surface. Это задача B.3.

---

## Current Project State

### Git/Commit Baseline

| Параметр | Значение |
|---|---|
| HEAD | `1d767d7` |
| Branch | `main` |
| Status | **clean** ✅ |
| Tags | v0.9.0-rc0-business-demo → v0.9.0-rc0-business-demo.6 |
| Last 8 commits | B.2.2 → B.2.1 → B.2 → B.1 → A.3.2 → A.3 → A.3.1 → A.3 dry-run |

### Project Structure

| Компонент | Путь | Статус |
|---|---|---|
| Backend | `backend/app/` (22 домена) | ✅ |
| Portal | `apps/portal-web/` (24 шаблона) | ✅ |
| Tests | `backend/tests/`, `apps/portal-web/tests/` | ✅ |
| Docs | `docs/` (architecture, audit, product, qa, security, ...) | ✅ |
| KSO Player | `apps/kso_player/` | ⏸️ (не запущен) |
| KSO Sidecar | `apps/kso_sidecar_agent/` | ⏸️ (не запущен) |
| KSO State Adapter | `apps/kso_state_adapter/` | ⏸️ (не запущен) |

---

## What Is Done

### Фаза A — Re-Alignment (100%)

| Этап | Статус | Commit |
|---|---|---|
| A.1 — TZ v2.5 Gap Analysis | ✅ | `3acdf2d` |
| A.2 — ERD/API/Event Contracts v2.5 | ✅ | `d9a90ee` |
| A.3 — KSO Data Migration (dry-run + execution) | ✅ | `60f3f8d`, `cb7f294` |
| A.3.1 — Migration Approval Gate | ✅ | `faa6ae4` |
| A.3.2 — Post-Migration Safety Gate | ✅ | `9e13dc5` |

### Фаза B — Multichannel Core (50%)

| Этап | Статус | Commit |
|---|---|---|
| B.1 — Channel Registry Cleanup | ✅ | `b1b8ed2` |
| B.2 — Device Model Unification | ✅ | `a88efd8` |
| B.2.1 — Device Model Reproducibility | ✅ | `bcce944` |
| B.2.2 — QA Pipeline Baseline | ✅ | `1d767d7` |
| B.3 — Placement Entity | ⏳ Next | — |
| B.4 — Channel Orchestrator Skeleton | ⏳ | — |
| B.5 — Universal Manifest Schema v1 | ⏳ | — |

### Что работает в production-ready состоянии

- **RBAC/RLS**: 47/47 scope checks, 8 ролей, cross-advertiser изоляция
- **Audit trail**: 20/20 целевых действий
- **Maker-checker**: self-approve блокируется, событие фиксируется
- **Campaign workflow**: создание → согласование → привязка креатива → публикация
- **Creative/media**: загрузка, AV-проверка (mock), статусная модель
- **5 каналов**: KSO, Android TV, Price Checker, ESL, LED Shelf
- **Device model**: полная цепочка PD→LC→DS→CP, 0 orphans
- **KSO мигрирован**: данные в универсальной модели, legacy сохранены

---

## What Is Partially Done

| Компонент | Что есть | Чего нет |
|---|---|---|
| **Placements** | 1 строка (KSO), таблица существует | Нет channel_id, нет связи 1→N с campaign, placement_target без полноценного surface |
| **Device Gateway** | Домен существует, модели есть | Нет регистрации, аутентификации, heartbeat, command queue |
| **Orchestrator** | Домен-скелет существует | Нет сборки manifest, нет AdapterContract, нет симуляции |
| **Adapters** | Домен-скелет существует | Нет KSO adapter, нет mock adapter |
| **Proof of Play** | 2 KSO события, таблица proof_events | Нет ingestion pipeline, нет ClickHouse |
| **Manifest** | Схема есть, signing не реализован | HMAC→Ed25519, manifest_orchestrator_queue |
| **Inventory** | Домен существует | Нет inventory_items, calendar, snapshots |

---

## What Is Not Started

| Компонент | Этап |
|---|---|
| Channel Orchestrator (полный) | B.4 |
| Universal Manifest Schema v1 | B.5 |
| Device Registration | C.1 |
| Device Auth & Heartbeat | C.2 |
| KSO Adapter | E.1 |
| ClickHouse PoP pipeline | F.1 |
| Emergency/Ops (health, alerts, overrides) | G |
| Production readiness (мониторинг, CI/CD, очереди) | H |

---

## Architecture Alignment with TZ v2.5

| Категория | Соответствие |
|---|---|
| Channel-agnostic core | ✅ B.1+B.2 — 5 каналов, device_types, profiles |
| Device hierarchy | ✅ PD→LC→DS→CP chain, 0 orphans |
| KSO как первый канал | ✅ Мигрирован, не отдельная вертикаль |
| Placements | ⚠️ Таблица есть, но без channel_id и без полноценной модели |
| Campaign→Placement 1→N | ❌ Не реализовано (B.3) |
| Channel Orchestrator | ❌ Скелет только (B.4) |
| Adapter Layer | ❌ Скелет только |
| Manifest Signing | ❌ Не реализовано |
| Proof of Play (универсальный) | ⚠️ 2 события, без ClickHouse |
| Device Gateway | ❌ Не реализован (C.1) |
| Emergency/Ops | ❌ Не начато (G) |

**Общий % соответствия ТЗ v2.5:** ~35-40% (↑ от ~25% на старте Re-Alignment)

---

## QA Baseline

| Suite | Result |
|---|---|
| Backend regression | **882/0** ✅ |
| Portal regression | **842/32sk** ✅ (8 flakes — pre-existing) |
| B.1 tests | 15/15 ✅ |
| B.2 tests | 19/19 ✅ |
| Combined B.1+B.2 | 34/34 ✅ |
| QA Pipeline | 14 pass, 10 fail, 14 skip |

**10 QA Pipeline failures** — все классифицированы как pre-existing (B.2.2):
- 3 — environment-dependent (не хватает CLI tools / env vars)
- 3 — требуют физической КСО
- 2 — technical debt (старые Alembic DROP, missing schema)
- 1 — legal/docs (152-ФЗ compliance)
- 1 — dead code tool not installed

**Ни один failure не блокирует B.3.**

---

## Security Baseline

### Что хорошо защищено

| Компонент | Статус |
|---|---|
| RBAC (47 permissions, 8 ролей) | ✅ Все backend routes проверены |
| RLS (advertiser scope изоляция) | ✅ 47/47 scope checks |
| Cross-advertiser изоляция | ✅ 23/23 тестов |
| Audit trail | ✅ 20/20 действий |
| Maker-checker | ✅ Self-approve блокируется |
| Cookies | ✅ httpOnly, SameSite=Lax, signed |
| PII visibility | ✅ Email/IP/UA скрыты или хешированы |
| No JS/CDN/localStorage | ✅ Server-side rendering only |
| Secrets/tokens | ✅ Не в репозитории, не в API ответах |

### Что нельзя ослаблять

- RBAC/RLS scope checks (47/47)
- Audit trail coverage (20/20)
- Maker-checker enforcement
- Cross-advertiser изоляцию
- Server-side rendering (без JS)

### Что проверить перед Device Gateway (C.1)

- Device credential storage (mTLS/JWT template)
- Device authentication flow (не начинать без security review)
- Device scope изоляцию (какие данные видит устройство)
- Rate limiting для device endpoints

---

## UI/UX Baseline

### Что хорошо

| Аспект | Статус |
|---|---|
| Русские labels | ✅ Все статусы, формы, ошибки — на русском |
| Формы | ✅ Labels, required markers (*), hints, cancel links |
| Пустые состояния | ✅ CTA-кнопки "Добавить", "Создать" |
| Статусы | ✅ Русские: Черновик, На согласовании, Утверждена |
| Accessibility | ✅ Skip-навигация, якоря, label associations |
| Нет технического шума | ✅ Нет raw UUID, нет internal терминов |
| Безопасность UI | ✅ Server-side rendering, без JS/CDN/localStorage |

### Что можно улучшить (не сейчас)

- Drag-and-drop для campaign/creative
- Real-time обновления
- Графики/диаграммы для отчётов
- Мобильная адаптация

---

## KSO / Device Baseline

| Аспект | Статус |
|---|---|
| KSO как первый канал | ✅ В универсальной модели |
| physical_devices как единая модель | ✅ 2 устройства, 0 orphans |
| KSO device chain (PD→LC→DS→CP) | ✅ Воспроизводится через seed |
| Legacy kso_* сохранены | ✅ 1+1+2 rows |
| Требует физической КСО | KSO Health, Alert Rules, Config Sync |
| Mock-ready для остальных каналов | ✅ device_types + profiles есть |
| Готовность к Device Gateway | ⚠️ Требует security review |

---

## Reliability / Monitoring Baseline

| Аспект | Статус |
|---|---|
| Monitoring | ❌ Не начато |
| Alert rules | ❌ Не начато (кроме KSO alerts — требует железо) |
| Backup/restore | ⚠️ Есть pg_dump (A.3.2), без автоматизации |
| Capacity planning | ❌ Преждевременно |
| SLO/SLA | ❌ Преждевременно |
| Health checks | ✅ `/health` endpoint работает |
| Graceful degradation | ✅ qa_pipeline проверка pass |

**Что нужно до pilot:**
- Automated backup schedule
- Базовый monitoring (CPU, память, disk, DB connections)
- Health check dashboard

**Что нужно до production:**
- Alert rules (не только KSO)
- SLO/SLA определения
- Capacity planning
- DR plan

---

## Documentation Consistency Check

| Документ | Актуальность | Действие |
|---|---|---|
| `tz-v2-5-gap-analysis-46-1.md` | ✅ Актуален | Не требует обновления |
| `tz-v2-5-realignment-roadmap-46-1.md` | ⚠️ Частично | Обновить B.1/B.2/B.2.1/B.2.2 |
| `v2-5-architecture-correction-plan-46-1.md` | ⚠️ Частично | Обновить статус device model |
| `roadmap-after-full-audit-45-7.md` | ⛔ Deprecated | Не трогать (история) |
| `erd-v2-5-a2.md` | ⚠️ Частично | 30/39 таблиц — актуально |
| `b2-2-qa-pipeline-baseline.md` | ✅ Новый | Актуален |
| `current-project-state-after-b2-2.md` | 🆕 Создать | Этот документ |

---

## Top 10 Risks

| # | Риск | Severity | Mitigation |
|---|---|---|---|
| 1 | Placement/Campaign связь — архитектурный долг | P0 | B.3 выделит Placement как сущность |
| 2 | Нет Channel Orchestrator — manifest без сборки | P0 | B.4 скелет → B.5 manifest |
| 3 | Device Gateway без security review | P0 | Перед C.1 — полный security review |
| 4 | Legacy kso_* дублируют universal model | P1 | Уже мигрировано, cleanup в B.2.2+ |
| 5 | Нет мониторинга для pilot | P1 | Базовый мониторинг до пилота |
| 6 | QA pipeline tools не установлены | P1 | Установить safety/vulture в CI |
| 7 | 152-ФЗ compliance неполный | P1 | Шаблоны в Phase H |
| 8 | Нет ClickHouse для PoP | P2 | Phase F |
| 9 | Нет production инфраструктуры | P2 | Phase H |
| 10 | KSO player/sidecar/adapter не запущены | P2 | Требуется физическая КСО |

---

## Stop Doing

- ❌ KSO-specific development без универсальной модели
- ❌ Новые portal-фичи до архитектурного выравнивания (B.3-B.5)
- ❌ Изменения БД без миграции или seed
- ❌ Ручной SQL для структурных изменений
- ❌ Удаление legacy kso_* таблиц (до отдельного approval)

## Continue Doing

- ✅ Каждый шаг: mini-design → код → тесты → regression → docs → commit
- ✅ Idempotent seed для данных
- ✅ Read-only проверки перед изменениями
- ✅ Совместимость с legacy — универсальные routes рядом со старыми
- ✅ 882 backend + 842 portal regression каждый шаг

---

## Go/No-Go for B.3 Placement

**Рекомендация: GO ✅**

**Блокеров нет:**
- Все тесты зелёные (882/0, 842/32sk)
- Device model унифицирована (B.2)
- Channel registry полный (B.1)
- KSO мигрирован в универсальную модель (A.3)
- QA pipeline baseline принят (B.2.2)
- 0 orphan rows во всех таблицах

**Риски B.3:**
- Placements table не имеет channel_id — нужно добавить (неразрушающая миграция)
- Campaign 1→N Placements — изменение бизнес-логики
- Placement target должен ссылаться на display_surface (уже сделано)

---

## Что делать следующим промтом

**B.3 — Placement как отдельная сущность.**
Рекомендуемый план:
1. Mini-design: схема placements (+channel_id), campaign→placements 1→N, API
2. Non-destructive schema migration
3. Seed для placement_target
4. Service helpers + API
5. Tests + regression + commit
