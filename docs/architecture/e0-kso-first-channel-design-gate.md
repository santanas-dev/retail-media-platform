# E.0 — Pre-E Audit / KSO First Channel Design Gate

> **Дата:** 2026-07-01
> **Этап:** E.0 — Design Gate (реализация не начинается)
> **Предыдущий:** D.6 Phase D Closure (commit `9b0c8ae`)
> **Результат:** ✅ GO для E.1 KSO Adapter Contract + Dry-Run Payload Builder

---

## 1. Executive Summary

**KSO — существующий production канал с legacy flow.** Universal model (Phase B) уже частично покрывает KSO (channel "kso", device_type "kso-pos", orchestrator контекст, universal manifest схема). **KSO Adapter** заполнит последний gap: построение channel-specific payload из универсального контекста, без нарушения legacy production path.

**Ключевой вывод:** Универсальная инфраструктура готова. KSO Adapter можно построить как dry-run channel adapter на существующем AdapterContract, без миграций, без API, без DB writes, без переключения production.

---

## 2. Current State After Phase D

| Фаза | Статус |
|---|---|
| A — Re-Alignment | ✅ |
| B — Multichannel Core | ✅ |
| C — Device Gateway | ✅ |
| D — Inventory & Planning | ✅ |
| **E — KSO First Channel** | **→ E.0 Design Gate сейчас** |

Backend: 1660 collected / 1613 passed / 47 pre-existing
Portal: 930 collected / 890 passed / 32 skipped

---

## 3. Existing Legacy KSO Flow

### 3.1 Что работает сейчас (production)

```
Campaign → Placement → Schedule → Publication Batch
  → generate_manifests()  [GeneratedManifest table]
  → publish_batch()
  → Device Gateway: GET /api/device-gateway/kso/{device_code}/manifest
  → kso_manifest_projection.build_kso_safe_manifest_projection()
  → KSO player получает манифест
```

### 3.2 Ключевые компоненты legacy

| Компонент | Файл | Назначение |
|---|---|---|
| GeneratedManifest | `manifests/models.py` | Хранит сгенерированный манифест (legacy) |
| KSO projection | `publications/kso_manifest_projection.py` | Строит safe KSO payload из GeneratedManifest |
| KSO media resolver | `publications/kso_media_ref_resolver.py` | Резолвит media refs для KSO |
| KSO PoP correlation | `device_gateway/kso_pop_correlation.py` | Коррелирует PoP events с KSO manifest |
| Gateway KSO endpoint | `device_gateway/router.py:136` | `GET /kso/{device_code}/manifest` |
| Gateway universal | `device_gateway/router.py` | `GET /manifest/universal/current` (dry-run) |

### 3.3 Где происходит DB write

- `generate_manifests()` → INSERT в `generated_manifests`
- `publish_batch()` → UPDATE статуса
- KSO projection — **read-only** (pure function, no DB calls)
- Gateway KSO endpoint — **read-only** (SELECT + projection)

---

## 4. Existing Universal KSO Chain

### 4.1 Channel Registry

Канал "kso" уже существует в `channels/seed.py`:
- `channel.code = "kso"`
- `device_type.code = "kso-pos"`
- `capability_profile` с portrait 768×1024

### 4.2 Orchestrator Context

`OrchestratorContext` строится цепочкой:
```
Placement → PlacementTarget → DisplaySurface → LogicalCarrier
  → PhysicalDevice → GatewayDevice
```

Для KSO placement с `channel_code="kso"` контекст резолвится полностью.

### 4.3 Universal Manifest Schema

`UniversalManifestV1` (B.5.1):
- `adapter_payload: ManifestAdapterPayload` — channel-specific данные
- `capability: ManifestCapability` — proof_type, resolution, orientation
- `targets: list[ManifestTarget]` — device_code, store_code, surface_code
- `FORBIDDEN_SECRET_KEYS` — валидация no-secrets

### 4.4 AdapterContract (B.4.1)

```python
class AdapterContract(ABC):
    adapter_name: str      # "kso"
    channel_code: str      # "kso"
    supports(channel_code, capability_profile) -> bool
    build_payload(context: OrchestratorContext) -> AdapterPayloadDraft
    validate_payload(payload: dict) -> list[str]
    simulate_delivery(payload: dict) -> AdapterSimulationResult
```

**KSO Adapter пока не реализован** — `OrchestratorContext` готов, `AdapterContract` готов, но `select_adapter("kso")` вернёт ошибку "no adapter registered".

---

## 5. Existing Gateway / Manifest Delivery

### Legacy path (production)

```
GET /api/device-gateway/kso/{device_code}/manifest
→ аутентификация устройства (JWT)
→ поиск latest GeneratedManifest
→ build_kso_safe_manifest_projection()
→ ETag/304
→ возврат KSO manifest
```

### Universal path (dry-run)

```
GET /api/device-gateway/manifest/universal/current
→ аутентификация устройства
→ build_manifest_context(placement, device)
→ select_adapter("kso") → ошибка (нет адаптера!)
→ build_adapter_payload → пропущен
→ assemble_manifest_draft → UniversalManifestV1 (без adapter_payload)
→ возврат universal manifest (dry_run=True)
```

### Gap

Universal endpoint **не может построить KSO adapter_payload** потому что `select_adapter("kso")` не находит адаптер. KSO Adapter — последний недостающий компонент.

---

## 6. Existing Orchestrator / Universal Manifest Flow

`orchestrator/service.py` предоставляет:

| Функция | Назначение |
|---|---|
| `build_manifest_context()` | Резолвит Placement → цепочку устройств |
| `check_capability_compatibility()` | Проверяет capability profile |
| `select_adapter(channel_code)` | Выбирает adapter по channel_code |
| `build_adapter_payload()` | Вызывает adapter.build_payload() |
| `assemble_manifest_draft()` | Собирает UniversalManifestV1 |

`manifests/universal_builder.py`:
- `build_universal_manifest_draft()` — вызывает orchestrator и собирает полный манифест
- Использует `select_adapter()` → **KSO adapter не зарегистрирован**

---

## 7. Planning / Inventory Readiness for KSO

| Аспект | Статус |
|---|---|
| InventoryUnit для KSO | ✅ возможно (channel_id → kso) |
| CapacityRule | ✅ |
| check_availability() для KSO placement | ✅ dry-run |
| check_conflicts() для KSO placement | ✅ dry-run |
| calculate_occupancy() для KSO | ✅ dry-run |
| Booking/reservation | ❌ deferred |
| Auto-reservation при campaign submit | ❌ deferred |

KSO placement **может пройти planning dry-run** — availability/conflicts/occupancy рассчитаются, но бронирование не создастся.

---

## 8. KSO Adapter Responsibility

### Что KSO Adapter должен делать

1. Зарегистрироваться в `select_adapter("kso")`
2. Реализовать `AdapterContract`:
   - `adapter_name = "kso"`
   - `channel_code = "kso"`
   - `supports("kso", ...)` → True
   - `build_payload(context)` → KSO payload draft
   - `validate_payload(payload)` → list ошибок
   - `simulate_delivery(payload)` → dry-run результат

### Что KSO Adapter НЕ должен делать

- ❌ Писать в `GeneratedManifest`
- ❌ Менять `generated_manifests` FK
- ❌ Вызывать `kso_manifest_projection`
- ❌ Менять `kso_placements` / `kso_devices`
- ❌ Переключать production KSO flow
- ❌ Вызывать `publish_batch()` / `generate_manifests()`
- ❌ Контактировать с реальными устройствами
- ❌ Содержать secrets / signed URLs

---

## 9. KSO Payload Mapping Design

### Mapping: OrchestratorContext → KSO payload

| KSO поле | Источник | Тип |
|---|---|---|
| `channel` | `context.channel_code` → "kso" | direct |
| `device_code` | `device.device_code` | direct |
| `store_id` / `store_name` | `device.store_id` (резолвить store) | transform |
| `placement_code` | `context.placement_code` | direct |
| `campaign_code` | `context.campaign_id` (резолвить) | transform |
| `items[].creative_code` | `context.creative_codes` | direct |
| `items[].media_type` | резолвить creative → mime_type | transform |
| `items[].duration` | резолвить creative → duration_ms | transform |
| `items[].order` / `slot_order` | индекс в creative_codes | derived |
| `items[].storage_ref` | резолвить creative → safe ref | transform |
| `schedule.start` / `end` | `context.start_date` / `end_date` | direct |
| `proof_type` | `capability.proof_type` | direct |
| `resolution` | `capability.resolution` | direct |
| `orientation` | `capability.orientation` | direct |

### What's missing / deferred

| Поле | Статус |
|---|---|
| `checksum` | deferred (нужен контент-hash) |
| `manifest_hash` | derived (можно из payload) |
| `version` / `schema_version` | direct (hardcoded) |
| `generated_at` / `timestamp` | derived (now) |
| `kso_placement_code` | ❌ запрещён в universal |

---

## 10. Compatibility Strategy

| Правило | Почему |
|---|---|
| Legacy KSO path — основной | Production не меняется |
| KSO Adapter — dry-run only | E.1/E.2 — только построение payload |
| Не писать в GeneratedManifest | FK/схема не меняется |
| Не менять `/kso/{device_code}/manifest` | Gateway endpoint untouched |
| Compatibility projection — отдельный gate | После E.3 |
| Real publish switch — отдельный approval | Не в Phase E |

**Production path остаётся неизменным.** KSO Adapter — новый, параллельный путь через универсальную модель.

---

## 11. Security / RLS / Audit

| Аспект | Статус в E.1 |
|---|---|
| Secrets в adapter payload | ✅ запрещены (FORBIDDEN_SECRET_KEYS) |
| Storage refs без signed tokens | ✅ только safe refs |
| Device auth — в Gateway | ✅ adapter не трогает auth |
| User auth — не для device | ✅ adapter не использует user auth |
| Audit events | ⏳ deferred до E.3+ |

### Будущие audit события (deferred)

- `kso.adapter.payload_built`
- `kso.adapter.validation_failed`
- `kso.adapter.simulated`

---

## 12. Data / Migration Decision

### E.1: **миграции не нужны**

- Adapter — чистый код (contract implementation)
- `select_adapter()` — реестр адаптеров (in-memory dictionary)
- Не нужны новые таблицы для dry-run adapter
- `OrchestratorContext` строится из существующих таблиц

### E.2–E.3: **миграции не нужны**

- KSO payload validation — pure function
- Universal manifest preview — использует существующий `UniversalManifestV1`

---

## 13. API Decision

### E.1: **API не нужен**

- Adapter — библиотека/модуль, не endpoint
- Регистрация в `select_adapter()` — кодовая
- Тестируется через unit tests
- Gateway универсальный endpoint уже существует — начнёт работать когда adapter зарегистрирован

### E.3: **Gateway endpoint auto-активируется**

- `GET /manifest/universal/current` — уже возвращает `UniversalManifestV1`
- Когда adapter зарегистрирован, `adapter_payload` заполнится автоматически
- Новый API не нужен

---

## 14. Test Strategy (для E.1–E.3)

### E.1 Tests (15+)

| Тест | Что проверяет |
|---|---|
| adapter_name == "kso" | ✅ |
| channel_code == "kso" | ✅ |
| supports("kso", ...) → True | ✅ |
| supports("not_kso", ...) → False | ✅ |
| build_payload from valid context | ✅ |
| payload has no secrets | ✅ |
| payload validates required KSO fields | ✅ |
| missing device_code → structured error | ✅ |
| missing content → warning/error | ✅ |
| no GeneratedManifest writes | ✅ |
| no publication flow imports | ✅ |
| no KsoPlacement dependency | ✅ |
| adapter register/select | ✅ |

### E.2 Tests (10+)

| Тест | Что проверяет |
|---|---|
| validate_payload valid | ✅ |
| validate_payload missing fields | ✅ |
| validate_payload wrong types | ✅ |
| validate_payload forbidden keys | ✅ |
| simulate_delivery success | ✅ |
| simulate_delivery failure | ✅ |
| no real delivery | ✅ |

### E.3 Tests (10+)

| Тест | Что проверяет |
|---|---|
| universal manifest includes adapter_payload | ✅ |
| adapter_payload.channel_code == "kso" | ✅ |
| Gateway universal endpoint returns filled payload | ✅ |
| Legacy KSO endpoint unchanged | ✅ |
| Planning suite unchanged (254/254) | ✅ |

---

## 15. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Adapter пересекается с legacy flow | Low | Dry-run only, разные code paths |
| KSO payload несовместим с игроком | Medium | validate_payload() + simulate_delivery() |
| select_adapter() реестр race condition | Low | In-memory dict, синглтон |
| Universal manifest случайно активируется в production | Low | dry_run=True всегда в Gateway |
| Planning ожидает booking для KSO | Low | Deferred — adapter только dry-run |

---

## 16. What Phase E Must Not Break

| Система | Гарантия |
|---|---|
| Legacy KSO endpoint (`/kso/{device_code}/manifest`) | ✅ untouched |
| `GeneratedManifest` таблица + FK | ✅ untouched |
| `kso_manifest_projection` | ✅ untouched |
| `kso_media_ref_resolver` | ✅ untouched |
| Gateway authentication (device JWT) | ✅ untouched |
| Publication flow (`generate_manifests`, `publish_batch`) | ✅ untouched |
| Device Gateway universal endpoint | ✅ расширяется, не ломается |
| Planning API + portal | ✅ untouched |
| Universal manifest schema | ✅ untouched (используется) |
| Backend collection (1660) | ✅ не регрессирует |
| Docker / .env | ✅ untouched |

---

## 17. Recommended Phase E Implementation Split

| Этап | Что | Статус |
|---|---|---|
| **E.0** | Pre-E Audit / KSO First Channel Design Gate | ✅ сейчас |
| **E.1** | KSO Adapter Contract + Dry-Run Payload Builder | → next |
| **E.2** | KSO Adapter Validation + No-Secrets Tests | → after |
| **E.3** | KSO Universal Manifest Preview Integration | → after |
| **E.4** | Legacy Compatibility / No Production Switch Gate | → after |
| **E.5** | Phase E Closure Gate | → final |

### E.1 Scope (минимальный)

1. `backend/app/domains/orchestrator/adapters/kso_adapter.py`:
   - `KsoAdapter(AdapterContract)`
   - `supports("kso")` → True
   - `build_payload(context)` → `AdapterPayloadDraft`
   - `validate_payload(payload)` → `list[str]`
   - `simulate_delivery(payload)` → `AdapterSimulationResult`

2. Регистрация в `select_adapter()`:
   - `_adapters["kso"] = KsoAdapter()`

3. Тесты: 15+ (adapter contract + payload building + no-secrets)

4. **Без миграций, без API, без DB writes**

---

## 18. GO/NO-GO

### GO ✅ для E.1 — KSO Adapter Contract + Dry-Run Payload Builder

**Причина:**
- Универсальная инфраструктура готова (Orchestrator, UniversalManifestV1, AdapterContract)
- KSO — единственный production канал с полной цепочкой
- KSO Adapter — последний недостающий компонент для universal manifest preview
- E.1 минимален: один класс (KsoAdapter), регистрация, 15+ тестов
- Без миграций, без API, без DB writes, без переключения production

**Риск:** низкий — dry-run adapter на существующем контракте, параллельно с production flow.
