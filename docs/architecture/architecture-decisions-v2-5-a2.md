# Architecture Decisions v2.5 — A.2

> **Дата:** 2026-06-29 | **Этап:** A.2  
> **Статус:** ПРОЕКТ — решения зафиксированы, требуют approval

---

## AD-1: Frontend — Server-side Jinja2 в v1

**Решение:** Server-side Jinja2 portal остаётся v1 frontend.

**Обоснование:** 
- Уже работает, 863 теста
- Безопаснее: нет JS, нет CDN, нет localStorage
- Меньше зависимостей
- Соответствует принципу «без внешних сервисов»

**Когда пересмотреть:** После реализации Device Gateway + Advertiser Portal (Фаза F). Если Advertiser Portal потребует интерактивности (drag-n-drop календари, интерактивные дашборды) — перейти на React+TypeScript.

**Статус:** ✅ СОГЛАСОВАНО (допустимо для v1)

---

## AD-2: Manifest Signing — HMAC v1 → Ed25519 production

**Решение:** HMAC-SHA256 для v1/mock, Ed25519 для production.

**Обоснование:**
- HMAC уже реализован в `core/security.py` (`sign_manifest`)
- Не требует PKI на старте
- Ed25519 — целевой алгоритм для production (асимметричный, device подписывает, сервер проверяет)

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-3: Mock Adapter обязателен

**Решение:** Mock Adapter реализуется ДО KSO Adapter. Позволяет тестировать Orchestrator → Adapter → Device Gateway цепочку без физического КСО.

**Обоснование:**
- ТЗ Section 24.6: «Для каждого адаптера должны быть реализованы mock-режим»
- 90% фазы B-C можно сделать без hardware
- Mock adapter эмулирует: heartbeat, manifest pull, PoP batch, ошибки

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-4: ClickHouse — до PoP production

**Решение:** ClickHouse вводится в фазе C.5 (до PoP production).

**Обоснование:**
- PostgreSQL справляется с demo/test данными
- ClickHouse нужен для: 40K устройств × heartbeat 30s × PoP
- Можно отложить до фазы C, но не дальше

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-5: Redis — не как единственная очередь

**Решение:** Redis используется для кэша, rate limiting, сессий (dev). Для PoP/device events — отдельная очередь (NATS/RabbitMQ/Redpanda).

**Обоснование:**
- ТЗ Section 24.9: «Redis допустим для простых задач и кэша, но архитектура должна позволять перейти на другой брокер»
- PoP события критичны для биллинга — нельзя терять
- Persisted messages + DLQ — обязательно

**Статус:** ✅ СОГЛАСОВАНО (очередь выбирается в фазе C)

---

## AD-6: publication_batch → Legacy

**Решение:** `publication_batches` — legacy. Целевой механизм: signed manifest через Channel Orchestrator.

**Обоснование:**
- publication_batch не подписан, не содержит adapter_payload, не версионирован
- Не соответствует manifest-контракту ТЗ v2.5
- Оставить как есть до реализации manifest_versions, затем мигрировать

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-7: Физическая КСО — не трогать до E.2

**Решение:** Физический КСО (192.168.110.223) не используется до фазы E.2.

**Обоснование:**
- Все фазы A-D реализуются на mock-данных
- E.1 (KSO Adapter) тестируется с mock device
- E.2 (Chromium Runtime) требует hardware

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-8: Server-side формы — без JS/CDN

**Решение:** Portal использует server-side rendering без JavaScript, CDN, localStorage.

**Обоснование:**
- Соответствует ограничениям безопасности (нет XSS через CDN)
- Работает внутри корпоративного контура без внешних зависимостей
- 863 теста подтверждают работоспособность

**Статус:** ✅ СОГЛАСОВАНО (уже реализовано)

---

## AD-9: No raw UUIDs in API — stable codes

**Решение:** API использует стабильные коды (campaign_code, placement_code, device_code, creative_code) вместо raw UUID.

**Обоснование:**
- Уже реализовано в campaign_code, creative_code, device_code
- Безопаснее: не раскрывает внутренние идентификаторы
- Стабильнее: код не меняется при миграциях

**Статус:** ✅ СОГЛАСОВАНО (уже реализовано)

---

## AD-10: KSO — первый канал, но не основа архитектуры

**Решение:** KSO реализуется первым production-каналом, но архитектура строится как channel-agnostic.

**Обоснование:**
- ТЗ v2.5 Section 24.1: «channel-agnostic core + channel-specific adapters»
- KSO-дубликаты таблиц (kso_devices, kso_placements) — нарушение этого принципа
- Миграция A.3 исправляет это

**Статус:** ✅ СОГЛАСОВАНО

---

## AD-11: Feature flags для staged rollout

**Решение:** Feature flags реализуются до production (фаза G).

**Обоснование:**
- ТЗ Section 22.9: обязательны для безопасного развития
- Критично для: нового алгоритма расписания, нового формата PoP, HTML5-контента
- Rollback через админку

**Статус:** ⏳ Отложено до фазы G

---

## Статус решений

| ID | Решение | Статус |
|---|---|---|
| AD-1 | Jinja2 v1 frontend | ✅ Согласовано |
| AD-2 | HMAC→Ed25519 manifest | ✅ Согласовано |
| AD-3 | Mock Adapter first | ✅ Согласовано |
| AD-4 | ClickHouse до PoP | ✅ Согласовано |
| AD-5 | Redis не очередь | ✅ Согласовано |
| AD-6 | publication_batch legacy | ✅ Согласовано |
| AD-7 | КСО до E.2 | ✅ Согласовано |
| AD-8 | No JS/CDN | ✅ Согласовано |
| AD-9 | Stable codes | ✅ Согласовано |
| AD-10 | KSO=первый канал | ✅ Согласовано |
| AD-11 | Feature flags | ⏳ Фаза G |
