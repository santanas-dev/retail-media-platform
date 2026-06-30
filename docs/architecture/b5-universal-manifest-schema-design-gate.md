# B.5.0 — Universal Manifest Schema v1 Design Gate

> **Дата:** 2026-07-01
> **Этап:** B.5 — Universal Manifest Schema
> **Статус:** Design Gate (только проектирование, без реализации)

---

## Executive Summary

B.5 проектирует **Universal Manifest Schema v1** — channel-agnostic формат манифеста,
который заменит текущий KSO-специфичный `GeneratedManifest`/`KsoSafeManifestProjectionResult`
на универсальную модель, способную обслуживать любые каналы: KSO, Android TV, ESL, LED shelf, price checker и т.д.

**B.5.0 — только Design Gate.** Код не пишется. Миграции не создаются. БД не меняется.

---

## 1. Current Legacy Manifest Flow

### 1.1 GeneratedManifest (таблица `generated_manifests`)

**Модель:** `backend/app/domains/manifests/models.py`

| Поле | Тип | FK |
|---|---|---|
| `id` | UUID PK | — |
| `manifest_code` | String(64) UNIQUE | — |
| `device_code` | String(64) | → `kso_devices.device_code` |
| `placement_code` | String(64) | → `kso_placements.placement_code` |
| `campaign_code` | String(64) | → `campaigns.campaign_code` |
| `status` | String(30) | — |
| `schema_version` | Integer (default=1) | — |
| `manifest_body_json` | JSON | — |
| `item_count` | Integer | — |
| `media_ref_format` | String(50) | — |
| `generated_by` | UUID | → `users.id` |
| `published_by` | UUID | → `users.id` |
| `generated_at` | DateTime | — |
| `published_at` | DateTime | — |

**Критические FK:** `device_code` → `kso_devices.device_code`, `placement_code` → `kso_placements.placement_code`.
Таблица **привязана к KSO** через эти FK.

### 1.2 Сборка манифеста: `build_manifest_from_placement()`

**Файл:** `backend/app/domains/manifests/service.py`

Поток:
```
placement_code → KsoPlacement (scheduling.models)
  → Campaign (campaign_code)
  → CampaignCreative → Creative → CreativeVersion (mime_type)
  → KsoDevice (device_code, store_id)
  → Store (code, is_active)
  → ManifestSourceItem
  → build_kso_safe_manifest_projection([item])
  → KsoSafeManifestProjectionResult (ok, manifest, items_included, errors)
```

**Выходной формат** (из `build_kso_safe_manifest_projection()`):
```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-...",
  "channel": "kso",
  "storeCode": "...",
  "deviceCode": "...",
  "items": [
    {
      "slotOrder": 0,
      "contentType": "image/png",
      "durationMs": 5000,
      "mediaRef": "media/current/slot-000",
      "validFrom": "...",
      "validTo": "..."
    }
  ]
}
```

**Проблемы:**
- `channel` жёстко закодирован как `"kso"`
- `deviceCode` и `storeCode` из KSO-сущностей
- Нет channel-agnostic metadata (capability profile, proof_type, adapter info)
- Нет подписи
- Нет adapters_payload
- Нет placement/campaign контекста (только codes)

### 1.3 Publication Flow

**Файл:** `backend/app/domains/publications/service.py`

`generate_manifests()` → ScheduleRun → ScheduleItem → InventoryUnit → Channel → Rendition → CreativeVersion → ManifestVersion → ManifestItem.
Тоже привязан к KSO через ScheduleItem/InventoryUnit.

### 1.4 Запись: `generate_manifest()` в manifests/service.py

```python
manifest = models.GeneratedManifest(
    manifest_code=data.manifest_code,
    device_code=device_code,
    placement_code=data.placement_code,
    campaign_code=placement.campaign_code,
    status="generated",
    ...
)
db.add(manifest)
await db.commit()  # ← DB WRITE
```

---

## 2. Current Orchestrator Draft Flow

### 2.1 `build_manifest_context()`

**Файл:** `backend/app/domains/orchestrator/service.py`

Разрешает универсальную цепочку:
```
Placement → Campaign (RLS: advertiser_id)
  → Channel (code, name)
  → PlacementTarget (target_type, store_id, display_surface_id)
  → DisplaySurface (resolution, capability_profile_id)
  → CapabilityProfile (orientation, formats, proof_type, interactive...)
  → LogicalCarrier
  → PhysicalDevice (external_code, status, device_type_id)
  → DeviceType (code)
```

**Выход:** `OrchestratorContext`:
- `placement_id`, `placement_code`, `campaign_id`, `channel_code`, `channel_name`
- `devices[DeviceInfo{device_id, device_code, store_id, status, surfaces[SurfaceInfo{surface_id, resolution, orientation, formats, proof_type, ...}]}]`
- `start_date`, `end_date`

### 2.2 `assemble_manifest_draft()`

**Выход:** `ManifestDraft` (dataclass, не DB-модель):
- `placement_code`, `channel_code`, `adapter_name`
- `context` — summary (placement_code, channel_code, device_count, surface_count)
- `adapter_payload` — channel-specific payload from adapter
- `status = "dry_run"`, `warnings`, `errors`

**Что УЖЕ есть:**
- Универсальная цепочка разрешена
- Device/surface/capability информация
- Adapter payload (channel-specific)
- RLS enforcement

**Чего НЕ хватает для Universal Manifest:**
- Campaign name, advertiser info
- Creative/rendition references
- Schedule info (dayparts, timezone)
- Playback config (loop, frequency)
- Signing info
- Provenance/metadata (generated_at, manifest_id)

### 2.3 `SimulationResult`

**Файл:** `backend/app/domains/orchestrator/simulation.py`

Структурированный dry-run результат:
- `placement_id`, `placement_code`, `campaign_id`, `channel_code`
- `ok`, `dry_run=true`, `target_count`, `surface_count`, `device_count`
- `adapter_name`, `payload_preview`, `warnings`, `errors[SimulationError]`
- `details.devices[{device_code, surfaces[]}]`

---

## 3. Universal Chain (уже работает)

```
Campaign (campaigns)
  └─ Placement (placements) — channel_id FK
       ├─ Channel (channels) — code, name
       └─ PlacementTarget (placement_targets)
            ├─ store_id → Store
            ├─ display_surface_id → DisplaySurface
            │    ├─ capability_profile_id → CapabilityProfile
            │    │    └─ resolution, orientation, formats, proof_type, interactive
            │    └─ logical_carrier_id → LogicalCarrier
            │         └─ physical_device_id → PhysicalDevice
            │              ├─ external_code (device_code)
            │              ├─ store_id
            │              └─ device_type_id → DeviceType → Channel
            └─ logical_carrier_id → LogicalCarrier
```

Все связи доступны через ORM. Orchestrator уже резолвит эту цепочку.

---

## 4. Universal Manifest v1 Goals

- **Channel-agnostic:** работать для KSO, Android TV, ESL, LED, price checker
- **Self-describing:** manifest содержит всё необходимое плееру без запросов к backend
- **Safe:** нет секретов, токенов, backend URL, внутренних ID
- **Versioned:** `manifest_version = "1.0"`
- **Extensible:** `adapter_payload` — channel-specific вложение
- **Signable:** структура готова к HMAC-подписи (но подпись — позже)
- **Compatible:** сосуществует с legacy `GeneratedManifest`, не ломает его

---

## 5. Universal Manifest v1 Non-Goals (B.5.0 + B.5.x)

- ❌ Не создаёт подпись (signing — позже, отдельная фаза)
- ❌ Не пишет в `generated_manifests` (legacy таблица не трогается)
- ❌ Не создаёт новую таблицу `universal_manifests` в B.5.0/B.5.1
- ❌ Не заменяет publication flow
- ❌ Не делает Device Gateway
- ❌ Не делает KSO Adapter
- ❌ Не делает public API
- ❌ Не делает real publish
- ❌ Не удаляет KSO legacy

---

## 6. Proposed Schema — Universal Manifest v1

### 6.1 Top-Level Structure

```json
{
  "manifest_version": "1.0",
  "manifest_id": "m-abc123-20260701-001",
  "generated_at": "2026-07-01T12:00:00+00:00",
  "schema_version": 1,
  "status": "draft",

  "campaign": {
    "campaign_id": "UUID",
    "campaign_code": "CAMP-001",
    "campaign_name": "Летняя акция",
    "advertiser_id": "UUID"
  },

  "placement": {
    "placement_id": "UUID",
    "placement_code": "PLC-001",
    "placement_name": "Размещение на КСО",
    "channel_code": "kso",
    "status": "approved",
    "priority": 0,
    "start_date": "2026-07-01",
    "end_date": "2026-07-31"
  },

  "targets": [
    {
      "target_type": "store",
      "store_code": "STORE-042",
      "store_name": "Магазин №42",
      "display_surface_code": "DS-KSO-MAIN",
      "display_surface_name": "Главный экран КСО",
      "logical_carrier_code": "LC-KSO-ZONE1",
      "logical_carrier_name": "Зона 1",
      "physical_device_code": "test-dev-seed",
      "physical_device_name": "КСО Тестовый",
      "device_type_code": "kso_checkout",
      "capability_profile_code": "kso_portrait_768x1024",
      "capability_profile_name": "KSO Portrait 768×1024"
    }
  ],

  "content": {
    "items": [
      {
        "creative_code": "CR-001",
        "creative_name": "Баннер акции",
        "media_type": "image/png",
        "rendition_ref": "rend/abc123",
        "format": "image/png",
        "duration_ms": 5000,
        "checksum": "sha256:...",
        "storage_ref": "creative/CR-001/v1/rendition.png"
      }
    ]
  },

  "schedule": {
    "start": "2026-07-01T00:00:00+03:00",
    "end": "2026-07-31T23:59:59+03:00",
    "timezone": "Europe/Moscow",
    "dayparts": [
      {"days": [1,2,3,4,5], "hours": "09:00-21:00"}
    ]
  },

  "playback": {
    "loop": true,
    "order": "sequential",
    "frequency": null
  },

  "adapter_payload": {
    "channel_code": "kso",
    "adapter_name": "KsoAdapter",
    "payload_schema_version": "1.0",
    "payload": {
      "...": "channel-specific fields"
    }
  },

  "security": {
    "signature_status": "unsigned",
    "signature": null,
    "canonical_hash": "sha256:..."
  },

  "capability": {
    "proof_type": "real_playback",
    "resolution": "768x1024",
    "orientation": "portrait",
    "formats": ["image/png", "image/jpeg", "video/mp4"],
    "max_file_size": 10485760,
    "max_duration": 86400000,
    "interactive": false
  },

  "metadata": {
    "dry_run": false,
    "source": "orchestrator",
    "build_id": "...",
    "warnings": [],
    "errors": []
  }
}
```

### 6.2 Field-Level Description

| Путь | Тип | Обязательное | Описание |
|---|---|---|---|
| `manifest_version` | string | ✅ | Семантическая версия схемы ("1.0") |
| `manifest_id` | string | ✅ | Уникальный детерминированный ключ |
| `generated_at` | ISO datetime | ✅ | Момент генерации |
| `schema_version` | integer | ✅ | Числовая версия (1) |
| `status` | enum | ✅ | draft/generated/published/revoked |
| `campaign.campaign_id` | UUID | ✅ | ID кампании (для audit) |
| `campaign.campaign_code` | string | ✅ | Безопасный код |
| `campaign.campaign_name` | string | ✅ | Человекочитаемое имя |
| `campaign.advertiser_id` | UUID | ⬜ | ID рекламодателя (для RLS) |
| `placement.*` | — | ✅ | Все поля placement |
| `placement.channel_code` | string | ✅ | Код канала |
| `targets[]` | array | ✅ | Минимум 1 target |
| `targets[].target_type` | string | ✅ | store/surface/carrier |
| `targets[].store_code` | string | ⬜ | Код магазина |
| `targets[].display_surface_code` | string | ✅ | Код поверхности |
| `targets[].physical_device_code` | string | ✅ | Код устройства |
| `targets[].device_type_code` | string | ⬜ | Тип устройства |
| `targets[].capability_profile_code` | string | ✅ | Профиль возможностей |
| `content.items[]` | array | ✅ | Минимум 1 creative |
| `content.items[].creative_code` | string | ✅ | Код креатива |
| `content.items[].media_type` | string | ✅ | MIME-тип |
| `content.items[].storage_ref` | string | ✅ | Безопасная ссылка без секретов |
| `schedule.start/end` | ISO datetime | ✅ | Период показа |
| `schedule.timezone` | string | ⬜ | Часовой пояс |
| `adapter_payload.channel_code` | string | ✅ | Код канала |
| `adapter_payload.adapter_name` | string | ✅ | Имя адаптера |
| `adapter_payload.payload_schema_version` | string | ✅ | Версия схемы payload |
| `adapter_payload.payload` | object | ✅ | Channel-specific данные |
| `security.signature_status` | enum | ✅ | unsigned/signed/invalid |
| `capability.proof_type` | string | ✅ | Тип пруфа из CapabilityProfile |
| `capability.resolution` | string | ✅ | Разрешение |
| `capability.formats` | array | ✅ | Поддерживаемые форматы |
| `metadata.dry_run` | boolean | ✅ | Флаг симуляции |
| `metadata.warnings/errors` | array | ⬜ | Предупреждения/ошибки |

---

## 7. Adapter Payload Boundary

**Универсальная часть** (поля выше `adapter_payload`) — общая для всех каналов.
Содержит: campaign, placement, targets, content, schedule, playback, capability, security, metadata.

**Channel-specific часть** (`adapter_payload.payload`) — определяется адаптером:
- KSO: `slotOrder`, `mediaRef`, `hiddenOnTouch`
- Android TV: `apk_package`, `min_android_version`, `deep_link`
- ESL: `template_id`, `update_interval`, `eink_mode`
- LED: `scroll_speed`, `brightness`, `color_mode`
- Price checker: `plu_list`, `price_format`

Валидация `adapter_payload.payload` — через `AdapterContract.validate_payload()`.
Универсальная часть валидируется общим ManifestValidator.

---

## 8. Versioning Strategy

| Поле | Значение | Смысл |
|---|---|---|
| `manifest_version` | `"1.0"` | Версия Universal Manifest Schema (SemVer) |
| `schema_version` | `1` | Целочисленная версия для быстрой проверки |
| `adapter_payload.payload_schema_version` | `"1.0"` | Версия схемы adapter payload |

**Forward compatibility:** новые поля добавляются с default=null, старые плееры их игнорируют.
**Backward compatibility с legacy:** legacy `GeneratedManifest.manifest_body_json` продолжает работать.
**Draft vs unsigned vs signed:** `status=draft` (dry-run), `status=generated` (unsigned), `security.signature_status=signed`.

---

## 9. Validation Rules

### Required fields
- `manifest_version` required
- `campaign` required (at minimum campaign_code)
- `placement` required (at minimum placement_code + channel_code)
- `targets` — at least one target required
- each target must have: `display_surface_code` + `physical_device_code` + `capability_profile_code`
- `content.items` — at least one item for final manifest (draft может быть пустым)
- `schedule.start/end` — required for final manifest

### No-secrets rules
- No `token`, `secret`, `password`, `credential`, `api_key`
- No `backend_url`, `minio`, `s3://`
- No internal UUIDs except campaign_id/placement_id (для audit)
- `storage_ref` — без токенов/подписанных URL (только path reference)

### Capability compatibility
- `content.items[].media_type` must be in `capability.formats`
- `proof_type` must match CapabilityProfile.proof_type
- `resolution` must match CapabilityProfile.resolution

### Adapter validation
- `adapter_payload.payload` валидируется через `adapter.validate_payload()`
- Если adapter validation fails → manifest invalid

---

## 10. Signing Design — Future Only (B.6+)

**B.5.0 не реализует подпись.** Проектируем поля:

- `security.signature_status`: `"unsigned"` → `"signed"` → `"invalid"`
- `security.signature`: null или base64-encoded HMAC-SHA256
- `security.canonical_hash`: SHA-256 canonical JSON (sort_keys, compact separators)
- **Canonical JSON ordering:** алфавитная сортировка ключей, `separators=(",", ":")`
- **Key management:** позже (фаза H или security hardening)
- **Проверка:** плеер проверяет signature_status=signed + валидирует подпись

---

## 11. Storage/DB Decision

### B.5.0–B.5.2: NO DB writes

- Schema и contracts — как Python dataclasses/Pydantic models
- Manifest builder — pure function из OrchestratorContext + adapter payload
- Валидация — pure function

### B.5.3+: Future proposal (НЕ реализовывать сейчас)

Предлагаемая структура для будущей таблицы `universal_manifests` (если понадобится):

```sql
universal_manifests (
    id UUID PK,
    manifest_id VARCHAR(128) UNIQUE,
    manifest_version VARCHAR(16),
    status VARCHAR(30),          -- draft/generated/published/revoked
    campaign_id UUID FK,
    placement_id UUID FK,
    channel_code VARCHAR(50),
    manifest_body_json JSONB,
    adapter_payload_json JSONB,
    signature_status VARCHAR(20), -- unsigned/signed/invalid
    signature TEXT,
    canonical_hash VARCHAR(128),
    generated_by UUID FK,
    generated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    ...
)
```

**НО:**
- `generated_manifests` не менять
- KSO legacy не удалять
- Совместимость через feature flag / shadow mode
- Решение о создании таблицы — отдельный design gate (B.5.3+)

---

## 12. API Decision

**B.5.1/B.5.2: NO public API.**

- Manifest builder — internal Python function
- Simulation использует существующий `simulate_placement()` (B.4.3)
- Preview можно через simulation result
- Device delivery — не в B.5 (это Device Gateway, фаза C)

**Future API (не в B.5):**
- `POST /api/manifests/preview` — preview из simulation
- `GET /api/manifests/{id}` — read manifest (RLS-gated)

---

## 13. Security/RLS Considerations

### No secrets
- `FORBIDDEN_KEYS` из `publications/kso_manifest_projection.py` расширяется на Universal Manifest
- Все те же запреты: token, secret, password, backend_url, minio, s3, internal IDs

### RLS
- Manifest preview/simulation наследует RLS через Placement → Campaign → advertiser_id
- Cross-advertiser доступ к manifest запрещён
- Использовать существующие `identity.rls` helpers

### Audit
- **B.5.0 не пишет audit events** (нет API, нет DB writes)
- Future audit actions (для B.5.3+):
  - `manifest.preview.generated` — preview manifest created
  - `manifest.validation.failed` — validation errors
  - `manifest.signed` — manifest signed
- `target_ref` = placement_code

---

## 14. Compatibility With Legacy GeneratedManifest

### Что можно маппить

| Universal Manifest v1 | Legacy GeneratedManifest |
|---|---|
| `placement.placement_code` | `placement_code` → KsoPlacement |
| `manifest_id` | `manifest_code` |
| `campaign.campaign_code` | `campaign_code` |
| `targets[].physical_device_code` | `device_code` → KsoDevice |
| `targets[].store_code` | `storeCode` |
| `content.items[].media_type` | `contentType` |
| `content.items[].duration_ms` | `durationMs` |
| `schedule.start/end` | `validFrom/validTo` |
| `manifest_version: "1.0"` | `schema_version: 1` |

### Что нельзя маппить без риска

| Universal Manifest v1 | Проблема |
|---|---|
| `adapter_payload` | Нет в legacy |
| `capability.*` | Нет в legacy |
| `playback.*` | Нет в legacy |
| `security.*` | Нет в legacy |
| `targets[]` (multiple) | Legacy — один device_code |

### Почему B.5 не должен сразу менять generate_manifests()

- `generate_manifests()` пишет в `generated_manifests` (production таблица)
- `generated_manifests` имеет FK к `kso_devices`, `kso_placements` — удаление сломает FK
- Publication flow зависит от KSO моделей
- Нужен compatibility adapter сначала, а потом migration

### Как позже сделать compatibility adapter

1. B.5.1: Universal Manifest Schema как Pydantic/dataclass
2. B.5.2: Manifest builder из OrchestratorContext
3. B.5.3: Validator + no-secrets checks
4. B.5.4: Compatibility layer — adapter для чтения legacy GeneratedManifest как UniversalManifest
5. B.6+: Signing implementation
6. B.7+: Migration plan (если нужна новая таблица)

---

## 15. Migration/Adoption Strategy

| Шаг | Что | Риск |
|---|---|---|
| B.5.1 | Schema-only (dataclasses/Pydantic) | Низкий |
| B.5.2 | Builder из B.4 OrchestratorContext | Низкий |
| B.5.3 | Validator + no-secrets + tests | Низкий |
| B.5.4 | Legacy compatibility read adapter | Средний |
| B.5.5 | Closure gate | Низкий |
| **B.6** | Signing implementation | Средний |
| **B.7** | Migration plan (если нужна новая таблица) | Высокий |
| **Phase C** | Device Gateway (manifest delivery) | Высокий |

**Feature flag:** `use_universal_manifest` (default=false) — включает universal manifest builder, но не ломает legacy.

---

## 16. Test Strategy (для B.5.1–B.5.3)

### Schema tests
- all required fields present
- no forbidden keys in canonical output
- `manifest_version` = "1.0"
- `schema_version` = 1

### Builder tests
- builds from OrchestratorContext + AdapterPayloadDraft
- target chain maps correctly to targets[] array
- device_type_code from chain, not hardcoded
- proof_type from CapabilityProfile
- formats from CapabilityProfile.formats_json

### Validation tests
- missing placement → rejected
- missing target → rejected
- empty targets → rejected
- unsupported format → rejected
- capability mismatch → rejected
- adapter validation fail → rejected
- unsigned manifest → signature_status="unsigned"

### Isolation tests
- no generated_manifests write
- publication flow unchanged
- legacy GeneratedManifest unchanged
- no KSO imports in manifest builder

### RLS tests
- cross-advertiser preview denied (через simulation)

### Canonical JSON tests
- stable key ordering for signing prep
- deterministic output for same input

---

## 17. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Legacy GeneratedManifest FK breakage | HIGH | Не трогать FK, compatibility adapter |
| Publication flow disruption | HIGH | Не менять publication service |
| Schema mismatch между каналами | MEDIUM | Adapter payload изолирован |
| Over-engineering schema до реальных нужд | MEDIUM | Только поля из ТЗ + chain resolution |
| Signing complexity | LOW | Отложено на B.6 |

---

## 18. What B.5 Must Not Touch

- ❌ `generated_manifests` таблица и FK
- ❌ `kso_placements`, `kso_devices`, `kso_*` таблицы
- ❌ Publication flow (`generate_manifests()`, `publish_batch()`)
- ❌ `manifests/service.py` (build_manifest_from_placement)
- ❌ `publications/service.py`
- ❌ `publications/kso_manifest_projection.py`
- ❌ Placement API
- ❌ Campaign submit validation
- ❌ Portal
- ❌ Orchestrator service/simulation (только read)
- ❌ Device Gateway
- ❌ Campaign targets (legacy)
- ❌ Docker/.env

---

## 19. Recommended B.5 Implementation Split

| Подэтап | Описание | DB writes | API |
|---|---|---|---|
| **B.5.0** | Design Gate (этот документ) | ❌ | ❌ |
| **B.5.1** | Manifest schema/contracts (dataclasses/Pydantic) | ❌ | ❌ |
| **B.5.2** | Manifest builder из OrchestratorContext | ❌ | ❌ |
| **B.5.3** | Validator + no-secrets + tests (25+ targeted) | ❌ | ❌ |
| **B.5.4** | Legacy compatibility analysis | ❌ | ❌ |
| **B.5.5** | Closure gate | ❌ | ❌ |

---

## 20. GO/NO-GO

### GO ✅ для B.5.1 — Universal Manifest Schema Contracts

**Основание:**
- Universal chain полностью резолвится через B.4 Orchestrator
- AdapterContract даёт channel-specific payload
- CapabilityProfile содержит proof_type, formats, resolution
- Все FK и legacy таблицы идентифицированы и защищены
- Schema дизайн покрывает все целевые каналы (KSO, Android TV, ESL, LED, price checker)
- B.5.1 — только dataclasses/Pydantic, без DB writes, без API

**Блокирующих рисков нет.**

---

## Рекомендуемый промт для B.5.1

```
Задача: выполнить B.5.1 — Universal Manifest Schema Contracts.
Создать dataclass/Pydantic модели для Universal Manifest v1
согласно docs/architecture/b5-universal-manifest-schema-design-gate.md.
Без DB writes. Без API. Без миграций.
```
