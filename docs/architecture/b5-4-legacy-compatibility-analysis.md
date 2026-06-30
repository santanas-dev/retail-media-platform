# B.5.4 — Legacy Compatibility Analysis for Universal Manifest v1

> **Дата:** 2026-07-01
> **Этап:** B.5.4 — Compatibility Analysis
> **Результат:** GO для B.5.5 — Option A (Parallel Preview)

---

## Executive Summary

Проанализирована совместимость Universal Manifest v1 (B.5.1–B.5.3) с текущим
legacy KSO manifest flow. Universal manifest может сосуществовать с legacy
без изменений production-пути. Рекомендован **Option A — Parallel Preview**:
Universal manifest используется только через preview/simulation; production
остаётся на legacy `GeneratedManifest`. Миграция на universal — отдельный
design gate (не B.5.x).

---

## 1. Current Legacy Manifest Flow

### 1.1 GeneratedManifest (таблица `generated_manifests`)

| Поле | FK | Привязка |
|---|---|---|
| `device_code` | → `kso_devices.device_code` | **KSO-specific** |
| `placement_code` | → `kso_placements.placement_code` | **KSO-specific** |
| `campaign_code` | → `campaigns.campaign_code` | Универсальное |
| `manifest_code` | UNIQUE | Универсальное |
| `status` | — | generated/published |
| `schema_version` | — | =1 |
| `manifest_body_json` | JSON | KSO-safe projection |

**Критические FK:** `device_code` → `kso_devices`, `placement_code` → `kso_placements`.
Нельзя удалять/менять без миграции и production downtime.

### 1.2 Legacy Manifest Body Format

```json
{
  "schemaVersion": 1,
  "generatedAt": "...",
  "channel": "kso",
  "storeCode": "STORE-042",
  "deviceCode": "test-dev-seed",
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

**Характеристики:**
- Single-device (один device_code)
- Single-store (один storeCode)
- Channel="kso" жёстко
- Нет capability блока
- Нет adapter_payload
- Нет подписи
- Нет multi-target

### 1.3 DB Write Points

| Функция | Пишет в |
|---|---|
| `generate_manifest()` | `generated_manifests` (INSERT + COMMIT) |
| `publish_manifest()` | `generated_manifests` (UPDATE status) |
| `generate_manifests()` | `manifest_versions` + `manifest_items` |
| `publish_batch()` | `publication_batches` (UPDATE status) |

**Все DB writes — через KSO-зависимые таблицы.**

---

## 2. Current Universal Manifest Flow

### 2.1 UniversalManifestV1 Structure

| Блок | Статус | Источник |
|---|---|---|
| `manifest_version` | ✅ "1.0" | Константа |
| `manifest_id` | ✅ `m-{date}-{hash8}` | Генерируется |
| `generated_at` | ✅ | datetime.now(utc) |
| `campaign` | ⚠️ Deferred | campaign_code=None |
| `placement` | ✅ | OrchestratorContext |
| `targets[]` | ✅ Multi-target | Device chain |
| `content[]` | ⚠️ Deferred | Empty + warning |
| `schedule` | ✅ | Placement dates |
| `playback` | ✅ | Surface proof_type |
| `adapter_payload` | ✅ | Adapter.build_payload() |
| `security` | ✅ unsigned | Константа |
| `capability` | ✅ | Surface profile |
| `metadata` | ✅ | Warnings/errors |

### 2.2 No DB Writes

Universal builder — pure function. `build_universal_manifest_from_draft()`:
- Не пишет в `generated_manifests`
- Не пишет ни в какую таблицу
- Не вызывает publish/generate
- Использует OrchestratorContext (read-only)

### 2.3 Deferred Fields

| Поле | Причина |
|---|---|
| `campaign.campaign_code` | OrchestratorContext не несёт campaign_code |
| `campaign.campaign_name` | Требует Campaign enrichment |
| `content[].creative_code` | Creative integration — отдельная фаза (F) |
| `content[].storage_ref` | Creative storage — deferred |
| `security.signature` | Signing — deferred (B.6+) |
| `capability.profile_code` | Profile code не резолвится в контексте |

---

## 3. Compatibility Matrix

### 3.1 Core Fields

| Legacy (KSO) | Universal v1 | Mapping | Risk | Notes |
|---|---|---|---|---|
| `schemaVersion` | `schema_version` | direct — int | Low | |
| `generatedAt` | `generated_at` | direct — ISO | Low | |
| `channel: "kso"` | `placement.channel_code` | transform | Low | Убрать hardcode KSO |
| `storeCode` | `targets[].store_code` | transform | Medium | Legacy single → universal multi |
| `deviceCode` | `targets[].physical_device_code` | transform | **High** | FK к kso_devices в legacy |
| — | `targets[].display_surface_code` | **missing in legacy** | Medium | Новая сущность |
| — | `targets[].capability_profile_code` | **missing in legacy** | Low | Новая сущность |
| — | `targets[].device_type_code` | **missing in legacy** | Low | Новая сущность |

### 3.2 Content Fields

| Legacy | Universal | Mapping | Risk | Notes |
|---|---|---|---|---|
| `items[].slotOrder` | `playback.order` | transform | Low | |
| `items[].contentType` | `content[].media_type` | direct | Low | |
| `items[].durationMs` | `content[].duration_ms` | direct | Low | |
| `items[].mediaRef` | `content[].storage_ref` | transform | **High** | Legacy = media/current/slot-NNN; Universal = creative/CR-.../path |
| `items[].validFrom` | `schedule.start` | direct | Low | |
| `items[].validTo` | `schedule.end` | direct | Low | |

### 3.3 Campaign/Placement

| Legacy | Universal | Mapping | Risk | Notes |
|---|---|---|---|---|
| `placement_code` → KsoPlacement | `placement.placement_code` | direct | Low | |
| `campaign_code` → campaigns | `campaign.campaign_code` | ⚠️ **deferred** | Medium | Не резолвится в контексте |
| — | `placement.placement_name` | **missing in legacy** | Low | |
| — | `placement.status` | **missing in legacy** | Low | |
| — | `campaign.campaign_name` | **missing in legacy** | Low | |
| — | `campaign.advertiser_id` | **missing in legacy** | Low | |

### 3.4 Capability/Proof

| Legacy | Universal | Mapping | Risk | Notes |
|---|---|---|---|---|
| — | `capability.proof_type` | **missing in legacy** | Low | Из CapabilityProfile |
| — | `capability.resolution` | **missing in legacy** | Low | |
| — | `capability.supported_formats` | **missing in legacy** | Low | |
| — | `capability.orientation` | **missing in legacy** | Low | |
| — | `playback.proof_type` | **missing in legacy** | Low | |
| — | `playback.loop` | **missing in legacy** | Low | |

### 3.5 Security/Signing

| Legacy | Universal | Mapping | Risk | Notes |
|---|---|---|---|---|
| — | `security.signature_status` | **missing in legacy** | Low | Всегда unsigned сейчас |
| — | `security.signature_algorithm` | **missing in legacy** | Low | Deferred |
| — | `security.content_hash` | **missing in legacy** | Low | Deferred |

### 3.6 Adapter/Metadata

| Legacy | Universal | Mapping | Risk | Notes |
|---|---|---|---|---|
| — | `adapter_payload.*` | **missing in legacy** | Low | Channel-specific |
| — | `metadata.dry_run` | **missing in legacy** | Low | |
| — | `metadata.warnings` | **missing in legacy** | Low | |
| — | `metadata.errors` | **missing in legacy** | Low | |
| — | `metadata.source` | **missing in legacy** | Low | |

---

## 4. Field Mapping Analysis

### Direct Mappings (4)
`schemaVersion` → `schema_version`, `contentType` → `media_type`, `durationMs` → `duration_ms`, `validFrom/To` → `schedule.start/end`

### Transform Mappings (4)
- `channel: "kso"` → `placement.channel_code` (unhardcode KSO)
- `storeCode` → `targets[].store_code` (single → multi)
- `deviceCode` → `targets[].physical_device_code` (FK к kso_devices)
- `mediaRef` → `storage_ref` (паттерн media/current/slot-NNN → creative/CR-...)

### Missing in Legacy (14)
`capability.*`, `adapter_payload.*`, `playback.*`, `security.*`, `metadata.*`, `placement_name`, `placement.status`, `campaign_name`, `advertiser_id`, `device_type_code`, `display_surface_code`, `capability_profile_code`

### Missing in Universal (Deferred) (2)
`campaign.campaign_code` (нет в OrchestratorContext), `content[].creative_code` (creative integration deferred)

### Not Safe to Map (2)
- `deviceCode` legacy FK → нельзя удалять kso_devices
- `placement_code` legacy FK → нельзя удалять kso_placements

---

## 5. Gaps and Deferred Fields

| Gap | Severity | Resolution |
|---|---|---|
| Campaign data incomplete | **MEDIUM** | B.5.5: документировать как deferred; enrich OrchestratorContext позже |
| Content/creative missing | **MEDIUM** | Фаза F или отдельный enrichment gate |
| Legacy single-device vs universal multi-target | **HIGH** | Compatibility adapter (не B.5.x) |
| Legacy generated_manifests FK | **HIGH** | Не трогать; отдельная таблица позже |
| Proof_type compatibility | LOW | Оба из CapabilityProfile (разные имена) |
| Signing absent in both | LOW | B.6+ |

---

## 6. Compatibility Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Legacy FK breakage** | 🔴 HIGH | Не трогать generated_manifests FK |
| **Publication flow disruption** | 🔴 HIGH | Не менять generate_manifests/publish_batch |
| **Single→multi target mismatch** | 🟡 MEDIUM | Compatibility adapter needed |
| **Dual source of truth** | 🟡 MEDIUM | Universal = preview; Legacy = production |
| **Storage_ref secret leakage** | 🟡 MEDIUM | No-secrets scanner проверяет оба |
| **Campaign code proxy** | 🟢 LOW | Исправлен в B.5.3 |
| **KSO hardcode в channel** | 🟢 LOW | Universal использует channel_code |

---

## 7. Coexistence Strategy

```
┌──────────────────────────────────────────────────────────┐
│                    Production Path                        │
│                                                          │
│  KsoPlacement → build_manifest_from_placement()          │
│    → build_kso_safe_manifest_projection()                │
│    → generate_manifest() → generated_manifests (DB)      │
│                                                          │
│  ✅ UNCHANGED — как было до B.5                           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                  Preview/Draft Path                       │
│                                                          │
│  Placement → build_manifest_context() (Orchestrator)     │
│    → UniversalManifestV1 (in-memory, no DB)              │
│    → validate_manifest_for_preview()                     │
│    → simulate_placement() (B.4.3)                        │
│                                                          │
│  ✅ Preview-only — не влияет на production                 │
└──────────────────────────────────────────────────────────┘
```

**Правила сосуществования:**
1. Legacy `GeneratedManifest` остаётся единственным production manifest-хранилищем
2. `UniversalManifestV1` — только preview/draft/internal
3. Никаких DB writes из universal builder
4. Никаких изменений в `generate_manifests()` / `publish_batch()`
5. Никаких изменений FK `generated_manifests`
6. Preview/simulation не вызывает KSO-специфичные функции

---

## 8. Future Options

### Option A — Parallel Preview Only ✅ RECOMMENDED NOW

**Описание:** Universal manifest строится только через preview/simulation.
Production остаётся на legacy `GeneratedManifest`.

**Плюсы:**
- Нулевой риск для production
- Не требует миграций
- Не требует KSO adapter
- Можно развивать universal schema независимо

**Минусы:**
- Два параллельных manifest-формата
- Universal manifest не доходит до устройств

**Когда:** B.5.4 + B.5.5 → далее фаза C (Device Gateway)

### Option B — Compatibility Projection

**Описание:** `UniversalManifestV1 → KsoSafeManifestProjectionResult`

**Плюсы:** Универсальный формат → legacy без изменений плеера

**Минусы:**
- Потеря multi-target (сжатие в single-device)
- Потеря capability блока
- Потеря adapter_payload
- Риск mismatch

**Когда:** После KSO adapter (фаза E), отдельный design gate

### Option C — New Universal Manifest Storage

**Описание:** `universal_manifests` + `universal_manifest_targets` + `adapter_payloads`

**Плюсы:** Полноценное хранилище без KSO FK

**Минусы:**
- Миграция БД
- Дублирование с generated_manifests
- Нужен feature flag

**Когда:** После B.5 + фазы C (Device Gateway), отдельный design gate

### Option D — Replace generated_manifests

**Описание:** Полная замена legacy таблицы

**Плюсы:** Единый source of truth

**Минусы:**
- 🔴 Высокий риск — production downtime
- 🔴 FK к kso_devices/kso_placements нельзя просто удалить
- 🔴 Publication flow завязан на KSO модели

**Когда:** НЕ РЕКОМЕНДУЕТСЯ. Только после полной миграции всех KSO-зависимостей.

---

## 9. Recommended Path

**Сейчас (B.5.4→B.5.5): Option A — Parallel Preview**

```
B.5.5 Closure Gate
    ↓
Фаза C: Device Gateway
    ↓  (manifest delivery через device gateway)
B.6: Signing Implementation
    ↓
Фаза E: KSO Adapter (реализует AdapterContract)
    ↓
Compatibility gate: Option B или C
```

---

## 10. Security / RLS / Audit

### RLS
- Preview simulation (B.4.3): Placement → Campaign → advertiser_id ✅
- Universal builder (B.5.2): наследует RLS через `build_manifest_context(current_user=...)` ✅
- Legacy flow: существующий RLS ✅

### No-Secrets
- Universal: `validate_no_secrets()` — 11 patterns ✅
- Legacy: `FORBIDDEN_KEYS` в `kso_manifest_projection.py` ✅
- Оба сканера независимы, не пересекаются

### Future Audit Events (не реализуются в B.5.x)

| Action | target_ref | Когда |
|---|---|---|
| `manifest.preview.generated` | placement_code | B.5.5+ (если preview API) |
| `manifest.validation.failed` | placement_code | B.5.5+ |
| `manifest.compatibility.checked` | placement_code | Option B gate |

---

## 11. Test Strategy

### Tests to Keep (уже работают)

| Тест | Статус |
|---|---|
| B.5.1 schema contracts | 37/37 ✅ |
| B.5.2 builder | 38/38 ✅ |
| B.5.3 validation | 40/40 ✅ |
| Legacy manifest tests | Existing (в общем test suite) ✅ |
| Backend collection | 1244, 0 errors ✅ |

### Tests to Add (будущие gate)

| Тест | Когда |
|---|---|
| Legacy flow unchanged after B.5 | B.5.5 closure |
| Universal preview does not affect legacy GeneratedManifest | B.5.5 |
| No cross-contamination (universal ↔ legacy) | B.5.5 |
| Compatibility matrix direct mappings verified | Option B gate |
| Secret scan on legacy mediaRef vs universal storage_ref | Option B gate |
| No FK change | B.5.5 |

---

## 12. What Must Not Change (confirmed)

- ❌ `generated_manifests` FK (kso_devices, kso_placements)
- ❌ `generate_manifests()` / `publish_batch()`
- ❌ `build_manifest_from_placement()`
- ❌ `build_kso_safe_manifest_projection()`
- ❌ KsoPlacement / KsoDevice models
- ❌ Publication flow
- ❌ Placement API / Portal
- ❌ Orchestrator service/simulation
- ❌ DB schema
- ❌ Docker/.env

---

## 13. GO/NO-GO

### GO ✅ для B.5.5 — Universal Manifest Closure Gate

**Основание:**
- Compatibility matrix полная (30+ полей)
- Coexistence strategy ясна (Option A)
- Риски идентифицированы и замитигированы
- Все тесты проходят (115/115 targeted, 1244 collected)
- Legacy production path полностью нетронут

**Блокирующих рисков нет.**
