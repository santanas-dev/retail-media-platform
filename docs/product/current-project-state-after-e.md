# Current Project State After Phase E

**Date:** 2026-07-01
**Последний commit:** f0cb794 (E.4)
**Фаза:** E (KSO First Channel) — COMPLETED

---

## Что готово

### Фазы A–D (Re-Alignment → Inventory)

- **A:** TZ v2.5 Gap Analysis, ERD/API/Event Contracts, KSO Data Migration — ✅
- **B:** Multichannel Core — Channel Registry, Device Types, Capability Profiles, AdapterContract, MockAdapter, Orchestrator — ✅
- **C:** Device Gateway Foundation — auth, heartbeat, manifest delivery, universal manifest endpoint, KSO legacy endpoint — ✅
- **D:** Inventory & Planning — InventoryUnit, CapacityRule, PlacementTarget, CampaignBooking, Planning API (5 read-only endpoints), Portal planning block — ✅

### Phase E: KSO First Channel

- **KsoAdapter** — dry-run adapter, реализует AdapterContract для channel_code="kso"
- **Universal preview** — KSO placement → select_adapter("kso") → KsoAdapter.build_payload() → UniversalManifestV1.adapter_payload
- **No-secrets** — 20 forbidden words, рекурсивный сканер, ALLOWED_SAFE_KEYS
- **Legacy isolation** — `/kso/{device_code}/manifest` не затронут, GeneratedManifest не пишется

## Текущие baselines

| Метрика | Значение |
|---|---|
| Backend collection | 1877 / 0 errors |
| E-series tests | 217/217 |
| E+B+C combined | 450/450 |
| Planning-only | 234/234 |
| Inventory | 20/20 |
| Planning+Inventory | 254/254 |
| Portal collection | 930 / 890 passed / 32 skipped / 8 pre-existing |

## KSO Adapter

```python
KsoAdapter(AdapterContract):
  adapter_name = "kso"
  channel_code = "kso"
  supports("kso") → True
  build_payload(context) → AdapterPayloadDraft (dry_run=True)
  validate_payload(payload) → list[str]
  simulate_delivery(payload) → AdapterSimulationResult (no network, no DB)
```

## Universal Preview для KSO

```
GatewayDevice → get_universal_manifest_for_device()
  → build_universal_manifest_preview()
    → select_adapter("kso") → KsoAdapter
    → build_adapter_payload() → AdapterPayloadDraft
    → build_universal_manifest_from_draft() → UniversalManifestV1
  → validate_no_secrets(manifest)
  → Response (dry_run, DRAFT)
```

## Что НЕ сделано (deferred)

- Real KSO production switch (не переключён)
- Compatibility projection (не сделан)
- GeneratedManifest writes из universal manifest (не пишется)
- Legacy KSO manifest replacement
- Signed manifests
- KSO player real compatibility (заблокирован hardware)
- KSO Chromium Runtime (заблокирован hardware)
- Media delivery/caching для KSO
- Proof/playback интеграция
- Booking/reservation интеграция
- Campaign submit auto-planning

## Следующий рекомендуемый этап

**Phase F: PoP & Analytics** — нормализованная proof-модель, campaign dashboard, advertiser portal.

Или **Phase E KSO Runtime** — при доступности KSO hardware (192.168.110.223).

Перед любым production switch для KSO — обязательный design gate.
