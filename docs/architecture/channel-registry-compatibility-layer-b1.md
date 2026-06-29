# Channel Registry Compatibility Layer — B.1

> **Дата:** 2026-06-29 | **Статус:** ACTIVE
> **Цель:** Задокументировать legacy↔universal mapping и правила перехода

## Legacy Routes (сохранены, не изменены)

| Route | Table | Permission | Статус |
|---|---|---|---|
| `GET /api/devices/kso` | `kso_devices` | `devices.read` | ✅ Active (legacy) |
| `GET /api/devices/kso/{device_code}` | `kso_devices` | `devices.read` | ✅ Active (legacy) |
| `POST /api/devices/kso` | `kso_devices` | `devices.manage` | ✅ Active (legacy) |
| `PUT /api/devices/kso/{device_code}` | `kso_devices` | `devices.manage` | ✅ Active (legacy) |

## Universal Routes (добавлены в B.1)

| Route | Table | Permission | Статус |
|---|---|---|---|
| `GET /api/channels` | `channels` | `channels.read` | ✅ Active |
| `GET /api/device-types?channel_id=...` | `device_types` | `devices.read` | ✅ Active |
| `GET /api/physical-devices?channel_code=kso` | `physical_devices` | `devices.read` | ✅ NEW (B.1) |
| `GET /api/physical-devices/by-code/{code}` | `physical_devices` | `devices.read` | ✅ NEW (B.1) |
| `GET /api/capability-profiles?device_type_id=...` | `capability_profiles` | `devices.read` | ✅ Active |
| `GET /api/logical-carriers?physical_device_id=...` | `logical_carriers` | `devices.read` | ✅ Active |
| `GET /api/display-surfaces?logical_carrier_id=...` | `display_surfaces` | `devices.read` | ✅ Active |

## Legacy Tables (сохранены, не удалены)

| Table | Row count | Мигрировано в | Статус |
|---|---|---|---|
| `kso_devices` | 1 | `physical_devices` | ✅ Read-only legacy |
| `kso_placements` | 1 | `placements` | ✅ Read-only legacy |
| `kso_proof_of_play_events` | 2 | `proof_events` | ✅ Read-only legacy |

## Transition Plan (НЕ выполнять без отдельного approval)

1. **Phase B.1 (сейчас)**: Universal routes добавлены, legacy сохранены
2. **Phase B.2+**: Portal начинает читать через universal routes
3. **Phase shadow**: Оба пути работают, сравниваются результаты
4. **Phase cleanup (отдельный approval)**: Legacy routes deprecated, потом удалены
5. **Phase final**: Legacy kso_* таблицы удалены

## Что нельзя удалять

- ⛔ `GET/POST/PUT /api/devices/kso/*`
- ⛔ `backend/app/domains/hierarchy/`
- ⛔ `kso_devices`, `kso_placements`, `kso_proof_of_play_events`
- ⛔ `backend/app/domains/manifests/service.py` (KSO manifest builder)

## Разрешённые изменения (текущая фаза)

- ✅ Добавление universal routes/helpers
- ✅ Seed device_types + capability_profiles
- ✅ Исправление багов (orientation, proof_type)
- ✅ Schema changes (external_code в API)
- ✅ Documentation
