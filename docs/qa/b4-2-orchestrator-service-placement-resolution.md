# B.4.2 — Orchestrator Service + Placement Target Resolution

**Date:** 2026-06-29  
**HEAD:** (to be filled)

---

## What was created

### `orchestrator/service.py`
- **7 error types:** PlacementNotFound, PlacementHasNoChannel, PlacementHasNoTargets, SurfaceChainIncomplete, CapabilityMismatch, UnsupportedChannel, AdapterValidationFailed — все наследуют HTTPException
- **ChainResult** dataclass — промежуточный результат резолва
- **ManifestDraft** dataclass — dry-run draft (не signed manifest)
- **8 functions:**

| Function | Description |
|---|---|
| `build_manifest_context` | Build context from placement → device chain, RLS enforced |
| `_resolve_chain` | Internal: placement → campaign → channel → targets → devices |
| `resolve_placement_targets` | Find targets, raise if zero |
| `resolve_surface_device_chain` | Surface → carrier → device → device_type → capability_profile |
| `check_capability_compatibility` | Validate orientation + formats per surface |
| `select_adapter` | Pick adapter from registry by channel_code, raise UnsupportedChannel |
| `build_adapter_payload` | Call adapter.build_payload(context) |
| `assemble_manifest_draft` | Assemble ManifestDraft (dry_run, no DB write) |

### Placement → Surface → Device chain
```
Placement
  → resolve_placement_targets() → PlacementTarget[]
    → resolve_surface_device_chain()
      → DisplaySurface → LogicalCarrier → PhysicalDevice
        → DeviceType → CapabilityProfile
```

### Adapter selection
- `select_adapter(channel_code)` → registry lookup
- Unsupported channel → `UnsupportedChannel` exception
- MockAdapter restricted to `channel_code='mock'` (B.4.2 fix)

### MockAdapter wildcard fix
- B.4.1 MockAdapter изменён: `supports()` теперь только для `channel_code='mock'`
- Negative test: `select_adapter("kso")` → UnsupportedChannel (нет adapter в registry)

### Unsupported channel detection
1. `get_adapter("kso")` → None
2. `select_adapter("kso")` → `raise UnsupportedChannel("kso")`
3. Не скрывается wildcard-адаптером

---

## What was NOT added

- ❌ No API endpoints
- ❌ No DB migrations
- ❌ No generated_manifests writes
- ❌ No publication flow changes
- ❌ No device_gateway imports
- ❌ No kso_placements imports
- ❌ No KSO adapter

---

## Tests: 57/57 (25 B.4.2 + 32 B.4.1)

| Group | Tests |
|---|---|
| Error types | 8 |
| Capability compatibility | 4 |
| Adapter selection | 2 |
| Payload + draft | 3 |
| DB chain resolution | 3 |
| Isolation checks | 5 |
| B.4.1 regression | 32 |

---

## Preserved

- ✅ Publication flow — unchanged
- ✅ generated_manifests — no imports/writes
- ✅ kso_placements — no imports
- ✅ kso_devices — no imports
- ✅ Placement API — unchanged
- ✅ Portal — unchanged

---

## GO/NO-GO

**GO for B.4.3 — Simulation Engine.**
