# E.3 — KSO Universal Manifest Preview Integration

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## Какой preview flow интегрирован

KsoAdapter интегрирован в существующий universal manifest preview path:

```
GatewayDevice → get_universal_manifest_for_device()
  → resolve_placement_for_gateway_device()
  → build_universal_manifest_preview()
    → build_manifest_context()      — резолвит цепочку Placement→Surface→Device
    → select_adapter("kso")         — возвращает KsoAdapter
    → build_adapter_payload(ctx)    — KsoAdapter.build_payload()
    → build_universal_manifest_from_draft(ctx, payload)
      → _build_adapter_payload()    — ManifestAdapterPayload в UniversalManifestV1
  → validate_no_secrets(manifest)   — проверка всего manifest включая adapter_payload
  → ETag/304 check
  → Response
```

**Никаких изменений кода не потребовалось** — интеграция уже работала с E.1 (KsoAdapter auto-register).

## Где KsoAdapter подключается

1. `select_adapter(context.channel_code)` в `build_universal_manifest_preview()` — при channel_code="kso" возвращает KsoAdapter
2. `build_adapter_payload(context, adapter)` — вызывает `KsoAdapter.build_payload()`
3. `_build_adapter_payload(payload_draft)` в универсальном билдере — маппит в ManifestAdapterPayload

## Как adapter_payload попадает в UniversalManifestV1

```python
# universal_builder.py:_build_adapter_payload()
ManifestAdapterPayload(
    channel_code=payload_draft.channel_code,    # "kso"
    adapter_name=payload_draft.adapter_name,    # "kso"
    payload_schema_version="1.0",
    payload=payload_draft.payload,              # KSO-safe dry-run payload
)

# universal_builder.py:build_universal_manifest_from_draft()
UniversalManifestV1(
    ...
    adapter_payload=adapter_payload,  # ← встраивается в manifest
    ...
)
```

## Подтверждения

### Dry-run only
- `KsoAdapter.build_payload()` всегда возвращает `dry_run: True`
- `UniversalManifestV1.status = ManifestStatus.DRAFT`
- `ManifestMetadata.dry_run = True`
- `AdapterPayloadDraft` никогда не содержит production-флагов

### No-secrets
- `validate_no_secrets(manifest)` в Gateway проверяет весь manifest включая `adapter_payload.payload`
- `model_dump()` манифеста рекурсивно проверяется на forbidden keys
- KsoAdapter.validate_payload() — вторая линия защиты (in-adapter)
- Все 20 forbidden words покрыты

### Legacy KSO production не изменён
- `/kso/{device_code}/manifest` — неизменён
- `kso_manifest_projection` — не импортируется universal builder-ом
- `GeneratedManifest` — не импортируется universal builder-ом
- `generate_manifests()` — не импортируется
- `publish_batch()` — не импортируется
- `KsoPlacement` / `KsoDevice` — не импортируются

### GeneratedManifest не пишется
- Universal preview path: `build_universal_manifest_from_draft()` — pure function
- Gateway endpoint: только read (резолвит placement), не пишет generated_manifests

---

## Тесты

**E.3 targeted:** 52 tests (все pass)

| Категория | Тестов |
|---|---|
| Adapter integration | 4 |
| Manifest preview with KSO | 16 |
| Gateway universal endpoint | 5 |
| No-secrets validation | 11 |
| Error handling | 6 |
| Read-only / production safety | 7 |
| Regression compatibility | 3 |

---

## Результаты suites

| Suite | Tests | Status |
|---|---|---|
| **E.3 targeted** | **52** | ✅ 52/52 |
| E.2 targeted | 65 | ✅ |
| E.1 targeted | 55 | ✅ |
| B.4 orchestrator | ~110 | ✅ |
| B.5 universal manifest | ~75 | ✅ |
| C gateway universal | ~48 | ✅ |
| E.1+E.2+E.3+B.4+B.5+C | **405** | ✅ |
| Planning-only | 234 | ✅ |
| Inventory | 20 | ✅ |
| Planning+Inventory | 254 | ✅ |
| Backend collection | **1832** | 0 errors |

---

## Baseline

| Метрика | До E.3 | После E.3 |
|---|---|---|
| Backend collection | 1780 | 1832 |
| Planning-only | 234/234 | 234/234 |
| Inventory | 20/20 | 20/20 |
| Planning+Inventory | 254/254 | 254/254 |
| E series | 120/120 | 172/172 |

---

## GO/NO-GO для E.4

**GO** ✅ — KSO universal manifest preview полностью интегрирован и верифицирован.
E.4 может переходить к KSO Adapter Payload Validation Hardening (усиление validate_payload,
SCHEMA-constrained payload, structured error codes).
