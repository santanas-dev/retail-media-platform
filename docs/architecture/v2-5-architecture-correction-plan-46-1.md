# TZ v2.5 Architecture Correction Plan — 46.1

> **Дата:** 2026-06-29
> **Основание:** Gap Analysis 46.1
> **Цель:** Привести текущий проект в соответствие с архитектурой ТЗ v2.5

## 1. Главный архитектурный долг: KSO-дубликаты

### Проблема

Текущий проект имеет ДВЕ параллельные модели носителей:

**Универсальная (v2.5):** channels → device_types → capability_profiles → physical_devices → logical_carriers → display_surfaces
**KSO-специфичная (legacy):** kso_devices, kso_placements, kso_proof_of_play_events

### Решение

**Мигрировать KSO в универсальную модель:**

```
kso_devices → physical_devices (channel_type='KSO')
kso_placements → универсальные placements (через Channel Orchestrator)
kso_proof_of_play_events → proof_events (нормализованная proof-модель)
```

### Что сохранить

- `kso_devices.device_code` → `physical_devices.external_code` (стабильный код)
- `kso_placements.placement_code` → универсальный `placements.placement_code`
- KSO-специфичные атрибуты (hidden_on_touch, ukms_version) → `device_properties` JSONB

### Что удалить

- Таблицы `kso_devices`, `kso_placements`, `kso_proof_of_play_events` после миграции
- KSO-специфичные роуты из hierarchy domain
- `kso_manifest_projection.py` → переписать как универсальный manifest projection

## 2. Отсутствующие компоненты v2.5

### 2.1. Channel Orchestrator

**Текущее:** `backend/app/domains/orchestrator/__init__.py` (пустой)

**Нужно:**
```
orchestrator/
  ├── __init__.py
  ├── models.py          # manifest_versions, manifest_targets, adapter_payloads
  ├── service.py         # сборка manifest, расчёт target surfaces
  ├── simulation.py      # симуляция перед публикацией
  ├── contracts.py       # интерфейс адаптера (AdapterContract)
  └── router.py          # API для публикации через orchestrator
```

### 2.2. Adapter Layer

**Текущее:** `backend/app/domains/adapters/` (нет файлов)

**Нужно:**
```
adapters/
  ├── __init__.py
  ├── base.py            # BaseAdapter (абстрактный контракт)
  ├── mock_adapter.py    # MockAdapter для тестов
  ├── kso_adapter.py     # KSO Adapter (первый production-канал)
  └── contracts.py       # AdapterContract: get_task, deliver_manifest, collect_proof
```

### 2.3. Device Gateway

**Текущее:** `backend/app/domains/device_gateway/` существует но без registration flow

**Нужно добавить:**
- `POST /device/register` — регистрация по device_code + hardware_fingerprint
- `GET /device/manifest` — pull manifest с ETag/304
- `POST /device/heartbeat` — heartbeat с capability profile
- `POST /device/pop/batch` — пакетная отправка PoP
- mTLS/JWT device auth (пока mock)

### 2.4. Manifest signing

**Текущее:** `backend/app/core/security.py` имеет `sign_manifest()` — но это HMAC, не production

**Нужно:**
- Универсальная manifest schema v1 (core + adapter_payload)
- Версионирование manifest (manifest_schema_version)
- Подпись (HMAC для v1, RSA/Ed25519 для production)
- Валидация совместимости (min_player_version, capabilities)

### 2.5. Нормализованная Proof-модель

**Текущее:** `proof_of_play_events` + `kso_proof_of_play_events`

**Нужно:**
- Единая таблица `proof_events` с полем `proof_type`
- Типы: `real_playback`, `delivery_ack`, `apply_ack`, `error/not_applied`
- Batch ingest с idempotency key
- ClickHouse для аналитики

## 3. План миграции (без потери данных)

### Фаза A: Подготовка ✅ COMPLETED

1. ✅ Создать миграцию: добавить `external_code` в `physical_devices` — **выполнено (A.3)**
2. ✅ Создать `device_properties` JSONB в `physical_devices` — **выполнено (A.3)**
3. ✅ Data migration: `kso_devices` → `physical_devices` — **выполнено (A.3, commit cb7f294)**
4. ✅ Feature flag: `USE_UNIVERSAL_DEVICE_MODEL` — **не реализован в коде (безопасно)**

### Фаза B: Device Model ✅ COMPLETED (B.1, B.2, B.2.1)

5. ✅ Channel registry: 5 каналов, 5 device types, 6 capability profiles (B.1)
6. ✅ Device model unified: PD→LC→DS→CP chain, 0 orphans (B.2)
7. ✅ Universal API: `/api/physical-devices?channel_code=`, `/by-code/`, `/surfaces` (B.1, B.2)
8. ✅ Seed reproducibility: KSO device chain в idempotent seed (B.2.1)
9. ⏸️ Portal device listing из универсальной модели — **отложено до B.3+**
10. ⏸️ Device gateway на universal model — **отложено до C.1**

### Фаза C: Очистка 📅 DEFERRED (отдельный approval)

11. ⏳ Удалить KSO-роуты и модели после подтверждения миграции
12. ⏳ Дропнуть `kso_devices`, `kso_placements`, `kso_proof_of_play_events`
    ⛔ **ЗАПРЕЩЕНО без отдельного approval**

## 4. Границы доменов (из ТЗ 24.3)

| Домен | Можно | Нельзя |
|---|---|---|
| Campaign | Статусы, workflow, рекламодатели | Технические детали плеера, vendor API |
| Inventory | Расчёт ёмкости, прогноз | Зависеть от конкретной таблицы КСО |
| Content | Креативы, renditions, MinIO | Публиковать на устройство напрямую |
| Channel | Каналы, device types, profiles | Менять бизнес-статусы кампаний |
| Proof | PoP, ACK, дедупликация | Принимать неподписанные события |
| Operations | Мониторинг, rollout | Обходить согласования и права |

## 5. Что НЕ менять

- ✅ RBAC/RLS модель (47/47 routes) — сохранить как есть
- ✅ Audit trail (20/20) — расширить на новые домены
- ✅ Campaign workflow — использовать как бизнес-ядро
- ✅ Portal server-side rendering — оставить для v1
- ✅ Hierarchy (branches/clusters/stores) — переиспользовать
- ✅ Security hardening (45.8.1) — сохранить все gates
