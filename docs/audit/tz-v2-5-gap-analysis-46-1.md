# TZ v2.5 Gap Analysis — 46.1 Re-Alignment

> **Дата:** 2026-06-29
> **Текущий HEAD:** `fe1e736` (46.1 compliance)
> **Baseline:** `v0.9.0-rc0-business-demo.6` → `e17900e`
> **Статус:** АУДИТ. Код не меняется.

## Executive Summary

### Ключевой вывод

**Текущая система — это НЕ production retail media platform. Это частично реализованный архитектурный каркас с развитым control-plane порталом, но без ключевых компонентов мультиканальной архитектуры v2.5.**

**Общий процент соответствия ТЗ v2.5: ~25%**

То, что построено — добротный control-plane (пользователи, RBAC/RLS, кампании, креативы, согласования, аудит, базовый inventory), но это лишь ~25% от полного ТЗ v2.5. Отсутствуют: Channel Orchestrator, Adapter Layer, Device Gateway, нормализованная Proof-модель, ClickHouse, event-driven delivery, emergency, operational health center.

### Что реально построено

| Компонент | Статус | Детали |
|---|---|---|
| Portal / Admin UI | ✅ DONE (но server-side, не React) | Кампании, креативы, согласования, admin, audit, inventory |
| RBAC/RLS | ✅ DONE (47/47 routes) | Полный контроль доступа |
| Audit trail | ✅ DONE (20/20 coverage) | Login + admin + business audit |
| Campaigns + Approvals | ✅ DONE | Полный workflow draft→approved→archived |
| Creatives + Media | ✅ PARTIAL | Загрузка, версии, но без multi-channel renditions |
| Hierarchy | ✅ DONE | Branches, clusters, stores |
| Channel model v2.5 | ✅ DONE (схема) | channels, device_types, capability_profiles, physical_devices, logical_carriers, display_surfaces |
| Publications | ✅ PARTIAL | Базовые publication_batches, но без manifest signing |
| Channel Orchestrator | ❌ NOT STARTED | Только пустой `__init__.py` |
| Adapter Layer | ❌ NOT STARTED | `adapters/` directory пуст |
| Device Gateway | ❌ NOT STARTED | Нет device registration, auth, heartbeat, manifest pull |
| PoP Ingestion | ❌ NOT STARTED | Нет batch ingest, ClickHouse, idempotency |
| ClickHouse | ❌ NOT STARTED | Только PostgreSQL |
| Emergency | ❌ NOT STARTED | Нет стоп-рекламы, emergency messages |
| Operational Health | ❌ NOT STARTED | Нет мониторинга устройств |
| Event-driven delivery | ❌ NOT STARTED | Прямые синхронные вызовы |
| Manifest signing | ❌ NOT STARTED | Нет crypto-подписи manifest |
| KSO Adapter | ❌ NOT STARTED | Нет Chromium kiosk wrapper |
| React frontend | ❌ DEVIATION | Server-side Jinja2 вместо React+TypeScript |
| Staged rollout | ❌ NOT STARTED | Нет |

## Детальный Gap Analysis по разделам ТЗ

### 4. Целевая архитектура продукта

| ID | Требование | Статус | Что есть | Чего нет | Приоритет |
|---|---|---|---|---|---|
| 4.1 | Логическое разделение компонентов | PARTIAL | Backend + Portal разделены | Нет Device Gateway, Content Service, Analytics, Emergency, Channel Adapter Layer | P0 |
| 4.2 | Технологический стек | DEVIATION | FastAPI ✅, PostgreSQL ✅, MinIO ✅, Redis ✅ | React ❌ (Jinja2 вместо React+TS), ClickHouse ❌, очередь событий ❌ | P0 |
| 4.3 | Размещение и сеть | NOT STARTED | Локальный dev | Нет mTLS, Device Gateway, отдельного device API | P1 |

### 6. Функциональные модули

| ID | Требование ТЗ | Статус | Приоритет |
|---|---|---|---|
| 6.1 | Пользователи, роли, доступ | DONE (RBAC/RLS 47/47, но без AD/SSO/MFA) | P1 |
| 6.2 | Рекламодатели, заказы, кампании | PARTIAL (есть advertisers, campaigns, но нет placement как отдельной сущности, нет A/B) | P1 |
| 6.3 | Рекламный инвентарь и прогноз | PARTIAL (базовые inventory tables, но нет conflict engine, forecast, sold out) | P1 |

### 7. Медиатека

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 7.1 | Поддерживаемые форматы | PARTIAL (загрузка, SHA-256, версии) но без multi-channel renditions, Creative QA check | P1 |

### 8. Плейлисты и Manifest

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 8.1-8.2 | Manifest | NOT STARTED (нет подписанного manifest, channel-specific adapter_payload, версионирования manifest schema) | P0 |

### 9. Плееры и runtime

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 9.1-9.2 | Плееры, автономность, fallback | NOT STARTED | P2 |

### 10. Управление устройствами

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 10 | Device registration, commands | NOT STARTED (есть kso_devices но без device gateway registration flow) | P1 |

### 11. Proof-of-Play

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 11.1-11.2 | PoP события | NOT STARTED (есть kso_proof_of_play_events но без batch, idempotency, подписей, ClickHouse) | P0 |

### 12. Аналитика

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 12 | Аналитика и отчётность | NOT STARTED (есть campaign_delivery_snapshots но без ClickHouse, дашбордов, экспорта PDF/XLSX) | P1 |

### 13. Emergency

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 13 | Emergency Management | NOT STARTED | P1 |

### 15. Структура данных

| ID | Требование ТЗ | Статус | Что есть | Чего нет | Приоритет |
|---|---|---|---|---|---|
| 15.1 | PostgreSQL ERD v2.5 | PARTIAL | channels, device_types, capability_profiles, physical_devices, logical_carriers, display_surfaces УЖЕ ЕСТЬ | kso_devices/kso_placements/kso_proof_of_play дублируют универсальную модель; нет surface_groups, store_zones, adapter_payloads, rollout_plans | P0 |
| 15.2 | ClickHouse | NOT STARTED | Только PostgreSQL | ClickHouse для PoP, heartbeats, аналитики | P1 |

### 21. Требования к Hermes

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 21.4 | Структура проекта | DEVIATION | `/backend` ✅, `/frontend` ❌ (React+TS нет, есть `apps/portal-web` на Jinja2), `/players` ❌ | P0 |
| 21.7 | Порядок реализации | WRONG ORDER | Начали с campaigns/creatives/portal раньше каналов и архитектурного каркаса | P0 |

### 23. Мультиканальное управление

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 23.1 | Channel-agnostic core | PARTIAL (модель каналов есть, но KSO-специфичные таблицы дублируют) | P0 |
| 23.3 | Physical → Logical → Surface | PARTIAL (модель есть, но не используется в campaigns/placements) | P0 |
| 23.4 | Multi-channel renditions | NOT STARTED | P1 |
| 23.5 | Manifest + adapters | NOT STARTED | P0 |

### 24. Архитектурная редакция v2.5

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 24.1 | Channel-agnostic core + adapters | PARTIAL (core tables есть, но KSO-дубликаты и нет адаптеров) | P0 |
| 24.2-24.3 | Слои и границы доменов | PARTIAL (домены разделены, но нет жесткого разделения Channel/Proof/Operations) | P0 |
| 24.4 | Channel → Device → Surface | PARTIAL (модель есть, но KSO bypass через kso_devices) | P0 |
| 24.5 | Channel Orchestrator | NOT STARTED (пустой `__init__.py`) | P0 |
| 24.6 | Channel Adapter Layer | NOT STARTED | P0 |
| 24.7 | Универсальный manifest | NOT STARTED | P0 |
| 24.8 | Нормализованная Proof-модель | NOT STARTED | P0 |
| 24.9 | Event-driven архитектура | NOT STARTED (синхронные вызовы) | P1 |
| 24.10 | Изменения в модели данных | PARTIAL (базовые таблицы есть, KSO-дубликаты — проблема) | P0 |

### 22. Production Best Practices

| ID | Требование | Статус | Приоритет |
|---|---|---|---|
| 22.1 | Бизнес-процесс размещения | PARTIAL (workflow есть, но нет коммерческого предложения, брони) | P2 |
| 22.2 | SLA и качество | NOT STARTED | P2 |
| 22.3 | Недопоказы и компенсации | NOT STARTED | P2 |
| 22.4 | Приоритеты и симуляция | NOT STARTED | P1 |
| 22.5 | Creative QA | NOT STARTED | P2 |
| 22.6 | Операционный центр здоровья | NOT STARTED | P2 |
| 22.7 | Staged rollout | NOT STARTED | P1 |
| 22.8 | Версионирование и неизменяемость | PARTIAL (есть версии креативов, но не manifest/placement/правил) | P1 |
| 22.10 | Наблюдаемость | NOT STARTED | P2 |

## Ключевые отклонения (DEVIATION)

### DEVIATION-1: Frontend — Jinja2 вместо React+TypeScript

**ТЗ:** `/frontend — React + TypeScript, административный интерфейс и личный кабинет рекламодателя`
**Факт:** `apps/portal-web` — server-side Jinja2 templates

**Оценка:** допустимо для v1/MVP, но требует явного решения. Server-side рендеринг имеет преимущества (нет JS, нет CDN, безопаснее), но не соответствует букве ТЗ.

### DEVIATION-2: KSO-дубликаты таблиц

**ТЗ:** Универсальная модель channel→device_type→physical_device→logical_carrier→display_surface
**Факт:** Существуют `kso_devices`, `kso_placements`, `kso_proof_of_play_events` ПАРАЛЛЕЛЬНО с `physical_devices`, `channels`, `capability_profiles`

**Риск:** Две параллельные модели данных. При добавлении Android/ESL/LED придётся либо создавать `android_devices`, либо мигрировать KSO на универсальную модель.

### DEVIATION-3: Campaign без Placement и без каналов

**ТЗ:** Campaign → Placement (где/когда/как) → Channel Orchestrator → Adapter
**Факт:** Campaign напрямую связан с campaign_targets, без отдельной сущности Placement и без маршрутизации через Orchestrator.

### DEVIATION-4: Publication Package ≠ Signed Manifest

**ТЗ:** Manifest подписан, версионирован, содержит adapter_payload
**Факт:** `publication_batches` — это не signed manifest. Нет криптоподписи, нет adapter_payload, нет совместимости с device gateway.

### DEVIATION-5: Порядок реализации (WRONG ORDER)

**ТЗ п.21.7:** 1. Каркас → 2. Модель данных → 3. Auth → 4. Hierarchy → 5. Device Gateway → 6. Медиатека → 7. Кампании → 8. Manifest → 9. Плееры → 10. PoP → 11. Аналитика → 12. Emergency → 13. Production
**Факт:** Сделаны шаги 1-4, 6-7, и много UI/UX/compliance hardening. Пропущены: Device Gateway, Channel Orchestrator, Manifest, PoP, ClickHouse.

## Stop/Go Решение

### Рекомендация: STOP текущую roadmap, START Re-Alignment

**Что остановить:**
1. ❌ Дальнейший UX hardening портала (46.2+)
2. ❌ Compliance 152-ФЗ (сделано достаточно для v1)
3. ❌ Развитие KSO-специфичных модулей без миграции на универсальную модель
4. ❌ Добавление новых фич в portal до реализации Device Gateway

**Что сохранить (control-plane slice):**
1. ✅ RBAC/RLS (47/47 routes) — gold standard, переиспользуется
2. ✅ Audit trail (20/20) — переиспользуется
3. ✅ Campaign workflow (draft→approved→archived) — как бизнес-ядро
4. ✅ Creative/media база — как основа Content Domain
5. ✅ Hierarchy (branches/clusters/stores) — переиспользуется
6. ✅ Channel model v2.5 (таблицы уже созданы) — расширить, убрать KSO-дубликаты
7. ✅ Portal server-side rendering — оставить как v1 frontend

**Что ДЕЛАТЬ ПЕРВЫМ (после этого анализа):**

P0 — Архитектурные блокеры:
1. Убрать KSO-дубликаты: мигрировать `kso_devices` → `physical_devices`, `kso_placements` → универсальные placements
2. Реализовать Channel Orchestrator (скелет + mock adapter)
3. Реализовать универсальный manifest schema v1 с подписью
4. Device Gateway: registration, auth, heartbeat, manifest pull (сначала mock)

P1 — До пилота:
5. Inventory calculation engine
6. Placement как отдельная сущность
7. PoP ingestion (batch, idempotency, ClickHouse)
8. KSO Adapter как первый production-канал

P2 — До production:
9. Emergency management
10. Analytics + advertiser portal
11. Operational health center
12. HA, backups, load testing

### Оценка архитектурного долга

| Долг | Стоимость исправления | Когда исправлять |
|---|---|---|
| KSO-дубликаты таблиц | Средняя (миграция данных) | **Сейчас** (P0) |
| Отсутствие Placement сущности | Средняя (refactor campaign→placement) | До пилота (P1) |
| Publication ≠ Manifest | Высокая (переписывание publication domain) | **Сейчас** (P0) |
| Server-side вместо React | Низкая (можно оставить для v1) | Опционально |
| Нет Device Gateway | Высокая (новый сервис) | **Сейчас** (P0) |
| Нет ClickHouse | Средняя (новая БД + миграция PoP) | До пилота (P1) |
| Нет event-driven доставки | Средняя (добавление очереди) | До пилота (P1) |

## Итоговая статистика

| Статус | Количество требований | % |
|---|---|---|
| DONE | ~8 из 35+ | ~23% |
| PARTIAL | ~12 из 35+ | ~34% |
| NOT STARTED | ~13 из 35+ | ~37% |
| DEVIATION | ~5 | — |
| WRONG ORDER | Да (начали с portal/campaigns раньше архитектурного каркаса) | — |

### Что мы реально построили:

**Архитектурный каркас (~25% от ТЗ v2.5) + Control-plane портал с качественным RBAC/RLS/audit**

Это НЕ demo — это рабочая админка с сильной безопасностью. Но это НЕ retail media platform — отсутствуют ключевые компоненты: Device Gateway, Channel Orchestrator, Adapter Layer, Manifest, PoP, ClickHouse, Emergency.
