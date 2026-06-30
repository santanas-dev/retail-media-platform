# B.4.1 — AdapterContract + MockAdapter

**Date:** 2026-06-29
**HEAD:** (to be filled)

---

## What was created

### `orchestrator/contracts.py`
- `SurfaceInfo`, `DeviceInfo`, `OrchestratorContext` — dataclasses
- `AdapterPayloadDraft`, `AdapterSimulationResult` — result types
- `AdapterContract` — ABC with 5 abstract members:
  - `adapter_name`, `channel_code` (properties)
  - `supports(channel_code, capability_profile)` → bool
  - `build_payload(context)` → AdapterPayloadDraft
  - `validate_payload(payload)` → list[str]
  - `simulate_delivery(payload)` → AdapterSimulationResult

### `adapters/mock_adapter.py`
- `MockAdapter` — always-compatible mock
- Channel-agnostic, no KSO-specific logic
- `validate_payload` checks: adapter="mock", channel, placement_code required
- `simulate_delivery` always returns ok=True, warns on 0 devices/surfaces

### `adapters/registry.py`
- `register_adapter(adapter)` — rejects duplicate channel_code
- `get_adapter(channel_code)` → AdapterContract | None
- `list_adapters()` → {channel_code: adapter_name}
- `clear_registry()` — test isolation

### `orchestrator/__init__.py`, `adapters/__init__.py`
- Clean exports

---

## What was NOT added

- ❌ No KSO adapter
- ❌ No Device Gateway
- ❌ No DB migrations
- ❌ No API endpoints
- ❌ No DB writes
- ❌ No imports from publications/manifests/device_gateway
- ❌ No references to generated_manifests, kso_placements, kso_devices

---

## Tests: 32/32

| Group | Tests |
|---|---|
| Abstract enforcement | 3 |
| supports() | 5 |
| build_payload() | 3 |
| validate_payload() | 6 |
| simulate_delivery() | 3 |
| Registry | 7 |
| Isolation checks | 5 |

---

## Preserved

- ✅ Publication flow — unchanged
- ✅ generated_manifests FK — unchanged
- ✅ kso_placements — unchanged
- ✅ Placement API — unchanged
- ✅ Portal — unchanged

---

## GO/NO-GO

**GO for B.4.2 — Orchestrator Service + Placement Target Resolution.**
