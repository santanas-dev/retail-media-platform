# F.0 — PoP & Analytics Design Gate

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## 1. Executive Summary

После Phase E (KSO First Channel — адаптер + universal preview) платформа готова к слою аналитики.
Два контура PoP уже существуют: legacy KSO (code-based, `proof_of_play/`) и enterprise Device Gateway (FK-based, `device_gateway/`).
Campaign Reports domain имеет схему `DeliveryMetrics` с 15+ метриками.
ClickHouse присутствует как зависимость, но не настроен.

**Рекомендация:** Phase F — построить read-only аналитический слой поверх существующих данных,
без миграций в F.1, с постепенным добавлением агрегаций и portal-отчётов.

---

## 2. Current State After Phase E

| Компонент | Статус |
|---|---|
| Device Gateway (auth, heartbeat, manifest) | ✅ Production |
| Universal Manifest (preview) | ✅ Preview только |
| KSO Adapter (dry-run) | ✅ Preview только |
| Legacy KSO PoP (code-based) | ✅ Production |
| Enterprise PoP (FK-based) | ✅ Production |
| Campaign Reports (DeliveryMetrics) | ✅ Схема готова |
| ClickHouse | ⚠️ Dep только, не настроен |
| Portal Analytics | ❌ Нет |

Backend baseline: 1877/0. Planning+Inventory: 254/254. E-series: 217/217.

---

## 3. Existing PoP / Playback / Proof Flow

### 3.1 Legacy KSO PoP (`proof_of_play/` domain)

**Модель:** `KsoProofOfPlayEvent` — code-based, без FK:
- `event_code`, `device_code`, `placement_code`, `campaign_code`, `creative_code`
- `media_ref`, `event_type`, `status`, `played_at`, `duration_ms`, `received_at`

**Endpoints:**
- `POST /api/device-gateway/kso/{device_code}/pop` — ingest (device auth)
- `GET /api/proof-of-play/test-kso` — list (reports.read, advertiser RLS)
- `GET /api/reports/pop` — production list (reports.read, advertiser RLS)
- `GET /api/reports/pop/summary` — aggregated summary (total_events, unique_devices/campaigns/creatives/placements, accepted/rejected/duplicate)

**Корреляция:**
- `device_code` → latest published `GeneratedManifest` → `KsoPlacement` → campaign_code, creative_code
- Safe projection: без raw UUIDs, tokens, secrets

### 3.2 Enterprise Device Gateway PoP (`device_gateway/` domain)

**Модели:**
- `ProofOfPlayEvent` — FK-based: `gateway_device_id`, `manifest_item_id`, `manifest_version_id`, `publication_target_id`, `schedule_item_id`, `campaign_id`, `campaign_rendition_id`, `rendition_id`, `creative_version_id`
- `ProofOfPlayBatch` — batch aggregation

**Endpoints:**
- `POST /api/device-gateway/pop/events` — single event ingest (device auth)
- `POST /api/device-gateway/pop/events/batch` — batch ingest (device auth)
- `GET /api/gateway-devices/{device_id}/pop-events` — admin list (devices.gateway.read)

**Корреляция:**
- `kso_pop_correlation.py` — server-side correlation KSO device → manifest item → internal IDs

### 3.3 Campaign Reports Domain

`DeliveryMetrics` — 15+ метрик:
- Publication: `planned_stores`, `planned_devices`, `published_targets`, `published_devices`, `publication_rate`
- Manifest: `manifest_available_devices`, `manifest_applied_devices`, `manifest_failed_devices`, `manifest_apply_rate`
- Cache: `cache_ready_devices`, `cache_missing_devices`, `cache_failed_devices`, `cache_invalid_hash_devices`
- Playback: `actual_play_count`, `unique_devices_with_pop`, `unique_stores_with_pop`, `last_pop_at`
- Health: `devices_ok`, `devices_warning`, `devices_critical`, `delivery_risk_status`

---

## 4. Existing Analytics / Reporting

| Компонент | Есть? | Детали |
|---|---|---|
| PoP event list (KSO) | ✅ | `/reports/pop` + `/proof-of-play/test-kso` |
| PoP summary (KSO) | ✅ | `/reports/pop/summary` |
| Device-level PoP (enterprise) | ✅ | `/gateway-devices/{id}/pop-events` |
| Campaign delivery metrics | ✅ Schema | `DeliveryMetrics` (не экспонирован) |
| Portal reports | ❌ | Только PoP list/summary через API |
| Occupancy reports | ✅ | Planning API read-only (D.5) |
| ClickHouse pipeline | ❌ | Dep установлен, не настроен |
| Scheduled aggregation | ❌ | Нет |
| Advertiser-facing analytics | ❌ | Нет |
| Store-level analytics | ❌ | Нет |

---

## 5. Target Phase F Scope

Phase F должен ответить на вопросы:

1. Какие устройства получили manifest?
2. Какие устройства подтвердили playback?
3. Сколько показов было по campaign / placement / store / device / channel?
4. Где расхождение planned vs delivered?
5. Где devices молчат (нет heartbeat/PoP)?
6. Какие PoP события не сопоставились с manifest?
7. Какие campaigns имеют delivery gaps?

---

## 6. Data Sources

| Источник | Данные | Связь |
|---|---|---|
| `gateway_devices` | device_code, channel_id, store_id, status, last_seen_at | Через channel_id → Channel |
| `ProofOfPlayEvent` | gateway_device_id, campaign_id, manifest_item_id, played_at | FK-based |
| `ProofOfPlayBatch` | gateway_device_id, batch_status | FK-based |
| `KsoProofOfPlayEvent` | device_code, campaign_code, placement_code, creative_code | Code-based |
| `Placement` | placement_code, campaign_id, channel_id, start_date, end_date | FK → Campaign |
| `PlacementTarget` | placement_id, display_surface_id, store-level данные | FK-based |
| `Campaign` | advertiser_id, status | FK → Advertiser |
| `ManifestVersion` | campaign_id, placement_id, published_at | FK-based |
| `ManifestItem` | manifest_version_id, creative_version_id | FK-based |
| `InventoryUnit` | campaign_id, placement_id, capacity, sold | Read-only |
| `CapacityRule` | inventory_unit_id, constraints | Read-only |
| `CampaignBooking` | campaign_id, inventory_unit_id | Read-only |
| `DeviceHeartbeat` | gateway_device_id, last_seen_at | FK-based |

---

## 7. Entity Mapping

```
PoP event (ProofOfPlayEvent) → gateway_device_id → GatewayDevice
  → GatewayDevice.channel_id → Channel
  → GatewayDevice.store_id → Store
  → GatewayDevice.physical_device_id → PhysicalDevice
    → PhysicalDevice → LogicalCarrier → DisplaySurface

PoP event → campaign_id → Campaign → advertiser_id → Advertiser
PoP event → manifest_item_id → ManifestItem → ManifestVersion
  → ManifestVersion.placement_id → Placement → campaign_id

KSO PoP (KsoProofOfPlayEvent) → device_code → KsoDevice
  → campaign_code → Campaign (по коду, не FK)
  → placement_code → KsoPlacement

Planning: Placement → Campaign, PlacementTarget → store scope
Inventory: InventoryUnit → Campaign, CapacityRule → InventoryUnit
```

**Важно:**
- Legacy KSO PoP использует code-based корреляцию (не FK)
- Enterprise PoP использует FK-based корреляцию
- Universal Manifest preview — НЕ production source для real delivery
- Dry-run preview events не должны смешиваться с production PoP

---

## 8. Metric Definitions

| Метрика | Источник | Формула | Ограничения |
|---|---|---|---|
| `delivered_impressions` | ProofOfPlayEvent + KsoPoP | COUNT where play_status='completed' | Только enterprise + KSO |
| `expected_impressions` | PlacementTarget × CampaignBooking × CapacityRule | SUM целевых показов | Требует schedule resolution |
| `proof_events_count` | ProofOfPlayEvent + KsoPoP | COUNT всех событий | — |
| `playback_success_count` | ProofOfPlayEvent | COUNT where play_status='completed' | Только enterprise |
| `playback_error_count` | ProofOfPlayEvent | COUNT where play_status='failed' | Только enterprise |
| `manifest_received_count` | ManifestRequest | COUNT where status != 'not_modified' | Нужна модель ManifestRequest |
| `device_last_seen` | GatewayDevice.last_seen_at или Heartbeat | MAX(last_seen_at) | — |
| `device_silent` | GatewayDevice | COUNT where last_seen_at < N hours ago | Порог конфигурируемый |
| `delivery_gap_percent` | expected vs delivered | (expected - delivered) / expected × 100 | Требует expected |
| `campaign_delivery_status` | DeliveryMetrics | Агрегация по campaign_id | — |
| `placement_delivery_status` | DeliveryMetrics | Агрегация по placement_id | — |
| `store_delivery_status` | GatewayDevice.store_id | Агрегация по store | — |
| `device_delivery_status` | GatewayDevice.id | На уровне устройства | — |

---

## 9. Source of Truth Decision

| Контур | Source of Truth | Использование |
|---|---|---|
| Legacy KSO production PoP | `KsoProofOfPlayEvent` | KSO production analytics |
| Enterprise Device Gateway PoP | `ProofOfPlayEvent` | Universal channel analytics |
| Dry-run preview manifest | `UniversalManifestV1` (не пишется) | **НЕ использовать как production proof** |
| Planning availability | `InventoryUnit` + `CapacityRule` (read-only) | Плановые метрики |

**Правило:** dry-run preview НЕ должен влиять на production analytics. Только `ProofOfPlayEvent` и `KsoProofOfPlayEvent` — источники для delivered-метрик.

---

## 10. Legacy KSO Production PoP vs Universal Preview

| | Legacy KSO PoP | Universal Preview |
|---|---|---|
| Модель | `KsoProofOfPlayEvent` | `UniversalManifestV1` (DRAFT) |
| Ingest | `POST /kso/{code}/pop` | Не пишется |
| Source | GeneratedManifest | OrchestratorContext |
| Analytics | ✅ Можно | ❌ Нельзя |
| Production | ✅ Да | ❌ Preview only |

**Dry-run exclusion rule:** Любой analytics pipeline должен фильтровать `manifest.metadata.dry_run == True` или `manifest.status == DRAFT`.

---

## 11. Dry-Run / Preview Exclusion Rules

1. `UniversalManifestV1.status == DRAFT` → исключить из production analytics
2. `UniversalManifestV1.metadata.dry_run == True` → исключить
3. `AdapterPayloadDraft` без соответствующего `ProofOfPlayEvent` → исключить
4. Events без `gateway_device_id` (только в KSO legacy) → обрабатывать отдельно
5. Events с `manifest_item_id = NULL` → помечать как unmatched, но не терять

---

## 12. Security / RLS / Audit Considerations

**Permissions (предложено, не реализовывать в F.0):**
- `analytics.read` — базовое право на просмотр аналитики
- `reports.read` — уже существует для PoP list/summary
- Advertiser scope: advertiser видит только свои campaigns
- Store scope: store manager видит только свои stores
- Operations/security_admin: видят device/store/channel health

**Audit events (предложено):**
- `analytics.report.viewed`
- `pop.events.queried`
- `delivery.gaps.viewed`

---

## 13. Privacy / Data Safety

- PoP events не содержат ПДн ✅
- KsoPoPListResponse исключает raw UUIDs, tokens, secrets ✅
- Device credentials не экспонируются ✅
- Advertiser scope enforced через RLS ✅
- Store scope через GatewayDevice.store_id
- Никакие internal secrets не попадают в analytics response

---

## 14. Data Model Strategy

**F.1 (schemas/contracts):**
- БЕЗ миграций
- Только read-only над существующими таблицами
- Новые Pydantic-схемы для агрегированных ответов

**F.2+ (агрегации):**
- Возможно: `delivery_facts` (материализованное представление)
- Возможно: `campaign_delivery_daily` (daily snapshot)
- Возможно: `device_delivery_health` (health snapshot)
- Каждая новая таблица — отдельный design gate

**ClickHouse:**
- НЕ в F.1
- Отдельный gate (F.6) когда volume потребует

---

## 15. API Decision

| Phase | API? | Что |
|---|---|---|
| F.1 | ❌ | Только schemas/contracts |
| F.2 | ❌ | Aggregation service (internal) |
| F.3 | ✅ | Analytics API: `GET /api/analytics/campaign/{id}`, `/placement/{id}`, `/store/{id}`, `/device/{id}` |
| F.4 | ✅ | Portal reports read-only |

---

## 16. Portal Decision

- F.1-F.3: Portal не меняется
- F.4: Portal получает read-only analytics blocks:
  - Campaign detail → delivery status block
  - Новый `/reports` раздел (доступен advertiser + operations)
  - Server-side rendering, без JS/CDN

---

## 17. ClickHouse Decision

- **НЕ в F.1-F.5**
- Отдельный gate (F.6) при:
  - PoP volume > 100K events/day
  - Аналитические запросы > 1s на PostgreSQL
  - Нужна real-time агрегация по 40K устройств

Текущий ClickHouse: зависимость установлена, конфиг stub, не используется.

---

## 18. Test Strategy

**F.1 tests (schemas/contracts):**
- PoP event mapping (KSO → универсальная модель)
- Unmatched event handling
- Duplicate event detection
- Event without manifest
- Event with unknown device
- No secrets in response schemas
- Dry-run preview excluded

**F.2-F.3 tests (aggregation + API):**
- Campaign aggregation correctness
- Placement aggregation
- Store aggregation
- Device health aggregation
- RLS advertiser scope
- Store scope
- No mutation (read-only)
- Legacy KSO production unchanged
- Device Gateway endpoints unchanged

**Safety tests (все фазы):**
- Planning suite pass
- E-series pass
- Backend collection 0 errors

---

## 19. Risks and Mitigations

| Риск | Вероятность | Влияние | Mitigation |
|---|---|---|---|
| Legacy KSO PoP ≠ Enterprise PoP модели | Высокая | Разные pipelines | Унифицировать на уровне API, не на уровне БД |
| Dry-run preview попадает в production analytics | Средняя | Неверные метрики | Фильтр по `dry_run=True` на уровне сервиса |
| ClickHouse нужен раньше чем планировалось | Низкая | Performance | PostgreSQL с индексами держит до 100K/день |
| Device-to-campaign связь неполная (code-based) | Средняя | Не все метрики доступны | Документировать ограничения, не блокировать |
| RLS/permissions сложность | Средняя | Задержка | Использовать существующий `reports.read` + advertiser scope |

---

## 20. Recommended Phase F Split

| Шаг | Что | Миграции? | API? | Portal? |
|---|---|---|---|---|
| **F.0** | PoP & Analytics Design Gate | ❌ | ❌ | ❌ |
| **F.1** | Analytics Schemas / Contracts | ❌ | ❌ | ❌ |
| **F.2** | PoP Mapping & Normalization Service | ❌ (read-only) | ❌ | ❌ |
| **F.3** | Delivery Aggregation Service | Возможно | ❌ | ❌ |
| **F.4** | Analytics API Read-Only | ❌ | ✅ | ❌ |
| **F.5** | Portal Analytics Read-Only | ❌ | ❌ | ✅ |
| **F.6** | ClickHouse / Performance Gate | Да | ❌ | ❌ |
| **F.7** | Closure Gate | ❌ | ❌ | ❌ |

---

## 21. GO/NO-GO for F.1

**GO** ✅ — F.1 может начинаться как schemas/contracts без миграций.

**Условия для GO:**
- Только Pydantic-схемы + контракты
- Без миграций
- Без API
- Без изменения существующих ingestion endpoints
- Без изменения legacy KSO PoP
- Без изменения Device Gateway production endpoints
- Dry-run preview исключён из production analytics по дизайну
