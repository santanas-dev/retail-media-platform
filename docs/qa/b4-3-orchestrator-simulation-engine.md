# B.4.3 — Orchestrator Simulation Engine

**Date:** 2026-06-29  

---

## What was created

### `orchestrator/simulation.py`
- **3 dataclasses:** SimulationResult, SimulationError, SimulationSummary
- **3 functions:** `simulate_placement`, `simulate_placements`, `summarize_simulation_results`

### How simulation works

```
simulate_placement(db, placement_id, current_user?)
  1. build_manifest_context() → resolve chain + RLS
  2. check_capability_compatibility() → orientation/formats
  3. select_adapter(channel_code) → registry lookup
  4. build_adapter_payload() → adapter payload draft
  5. adapter.validate_payload() → validation
  6. assemble_manifest_draft() → dry_run draft
  → SimulationResult {ok, warnings, errors, payload_preview}
```

### SimulationResult fields
- placement_id, placement_code, campaign_id, channel_code
- ok, dry_run (always true)
- target_count, surface_count, device_count
- adapter_name, payload_preview (safe: no raw payload)
- warnings[], errors[SimulationError]
- details {devices: [{device_code, surfaces}]}

### Error handling
All expected errors caught and returned as SimulationError:
- placement_not_found → step=resolve_context
- placement_no_channel → step=resolve_context
- placement_no_targets → step=resolve_context
- access_denied → step=resolve_context (RLS 403)
- capability_mismatch → step=capability_check
- unsupported_channel → step=select_adapter
- adapter_validation_failed → step=validate_payload

### What simulation does NOT do
- ❌ No DB writes
- ❌ No generated_manifests creation
- ❌ No publication status changes
- ❌ No device communication
- ❌ No KSO legacy references

---

## Tests: 79/79 (22 B.4.3 + 25 B.4.2 + 32 B.4.1)

| Group | Tests |
|---|---|
| Result structure | 4 |
| Simulation flow (mock) | 10 |
| Batch + summary | 3 |
| Import boundaries | 5 |
| B.4.2 regression | 25 |
| B.4.1 regression | 32 |

---

## Preserved

- ✅ Publication flow — unchanged
- ✅ generated_manifests — no imports/writes
- ✅ kso_placements — no imports
- ✅ Device Gateway — no imports
- ✅ Placement API — unchanged
- ✅ Portal — unchanged

---

## GO/NO-GO

**GO for B.4.4 — Orchestrator Closure Gate.**
