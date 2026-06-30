# B.4.0 — Channel Orchestrator Design Gate

**Date:** 2026-06-29
**HEAD:** `fd7002f`
**Status:** DESIGN GATE — no code written

---

## Executive Summary

B.4.0 определяет архитектуру Channel Orchestrator — слоя между Placement/Campaign и Channel Adapters. Orchestrator отвечает за: резолвинг target surfaces → device chain → выбор adapter → сборка adapter_payload → dry-run simulation. Он **не** пишет в generated_manifests, **не** меняет publication flow, **не** отправляет на устройства. AdapterContract — channel-agnostic интерфейс для будущих KSO/Android TV/ESL адаптеров. B.4 разделён на 4 подэтапа: contracts (B.4.1), service (B.4.2), simulation (B.4.3), closure (B.4.4). Миграций и API на B.4 не требуется.

---

## Current State Before B.4

### Domain Inventory

| Domain | Files | State |
|---|---|---|
| `orchestrator/` | `__init__.py` only | Empty skeleton |
| `adapters/` | `__init__.py` only | Empty skeleton |
| `manifests/` | `models.py`, `service.py`, `router.py` | Active — `build_manifest_from_placement()` |
| `publications/` | `service.py`, `router.py` | Active — batch publish pipeline |
| `channels/` | `models.py`, `service.py`, `placements_router.py` | Active — Placement + PlacementTarget |
| `campaigns/` | `models.py`, `service.py`, `router.py` | Active — Campaign.placements |
| `device_gateway/` | `router.py`, `models.py` | Active — device registration |

### Key Gap

Manifest generation currently uses **KsoPlacement** (legacy, `scheduling/models.py`). The new universal **Placement** model (B.3) is not yet wired into manifest generation. B.4 Orchestrator will be the bridge.

---

## Existing Publication/Manifest Flow

```
Campaign (approved)
  └─ create_batch_from_campaign()
       └─ PublicationBatch (draft)
            ├─ request_batch_approval()
            ├─ approve_batch()
            └─ generate_manifests()  ← publications/service.py
                 └─ build_manifest_from_placement()  ← manifests/service.py
                      └─ KsoPlacement (legacy model)
                           └─ build_kso_safe_manifest_projection()
                                └─ GeneratedManifest (DB write)
                                     ├─ FK → kso_devices.device_code
                                     ├─ FK → kso_placements.placement_code
                                     └─ FK → campaigns.campaign_code
```

**Why B.4 must not change this:**
- PublicationBatch → approve → generate → publish — production flow
- GeneratedManifest FK chain (kso_devices, kso_placements, campaigns) — validated
- B.4 Orchestrator sits **before** generate_manifests, providing adapter_payload

---

## Existing Placement/Surface/Device Chain

```
Campaign (1)
  └─ Placements (N)
       ├─ channel_id → Channel (kso, android_tv, ...)
       └─ targets (N) → PlacementTarget
            ├─ target_type = 'store'    → store_id
            ├─ target_type = 'surface'  → display_surface_id → DisplaySurface
            │    ├─ logical_carrier_id  → LogicalCarrier
            │    │    └─ physical_device_id → PhysicalDevice
            │    │         ├─ device_type_id → DeviceType → Channel
            │    │         └─ (store_id)
            │    └─ capability_profile_id → CapabilityProfile
            │         ├─ resolution, orientation, formats
            │         ├─ proof_type, interactive, cache_policy
            │         └─ max_file_size, max_duration
            └─ target_type = 'carrier' → logical_carrier_id
```

**Role in B.4:** Orchestrator resolves this chain to build adapter_payload context.

---

## Domain Boundaries

| Domain | Responsibility | B.4 interaction |
|---|---|---|
| **Campaign** | Business workflow, approval, submit | Read-only (scope inheritance) |
| **Placement** | Where/when/which channel/which surfaces | Primary input to Orchestrator |
| **Orchestrator** | Resolve chain → select adapter → build payload → simulate | This is B.4 |
| **Adapter** | Channel-specific payload building | Called by Orchestrator |
| **Publication** | Batch approval + publish + delivery | NOT touched by B.4 |
| **Manifest** | Generate + store manifests | Called by Publication, NOT by B.4 |
| **Device Gateway** | Device registration, heartbeat, PoP | NOT in B.4 (Phase C) |

---

## Orchestrator Responsibility

### What Orchestrator Does

1. Accept Placement (or list of Placements)
2. Resolve target surfaces: PlacementTarget → DisplaySurface → LogicalCarrier → PhysicalDevice → DeviceType → Channel → CapabilityProfile
3. Check channel/capability compatibility
4. Select adapter by `channel_code`
5. Build `adapter_payload` draft via adapter
6. Return simulation result (warnings/errors)
7. Provide manifest context for future B.5 manifest generation

### What Orchestrator Is NOT

- ❌ Does NOT write to `generated_manifests`
- ❌ Does NOT change publication batch status
- ❌ Does NOT send manifests to devices
- ❌ Does NOT generate manifests (delegates to manifests domain in B.5)
- ❌ Does NOT replace Publication flow
- ❌ Does NOT handle device registration/communication (Phase C)
- ❌ Does NOT ingest PoP events (Phase C/F)

---

## AdapterContract Design

```python
# Conceptual interface (ABC) — implementation in B.4.1

class AdapterContract(ABC):
    """Channel-agnostic adapter interface."""

    @property
    @abstractmethod
    def adapter_name(self) -> str: ...

    @property
    @abstractmethod
    def channel_code(self) -> str: ...

    @abstractmethod
    def supports(
        self, channel_code: str, capability_profile: CapabilityProfile
    ) -> bool: ...

    @abstractmethod
    async def build_payload(
        self, context: OrchestratorContext
    ) -> dict: ...

    @abstractmethod
    def validate_payload(self, payload: dict) -> list[str]: ...

    @abstractmethod
    async def simulate_delivery(
        self, payload: dict
    ) -> SimulationResult: ...
```

### Channel-agnostic: adapter works with any channel that implements the contract.
### KSO adapter: NOT implemented in B.4. Only MockAdapter in B.4.1.

---

## Mock Adapter Design (B.4.1)

```python
class MockAdapter(AdapterContract):
    """Always-compatible mock for testing."""
    adapter_name = "mock"
    channel_code = "mock"

    def supports(self, channel_code, capability_profile) -> bool:
        return True  # Always compatible

    async def build_payload(self, context) -> dict:
        return {
            "adapter": "mock",
            "channel": context.channel_code,
            "placement_code": context.placement_code,
            "surfaces": len(context.surfaces),
            "device_count": len(context.devices),
        }

    def validate_payload(self, payload) -> list[str]:
        return []

    async def simulate_delivery(self, payload) -> SimulationResult:
        return SimulationResult(ok=True, warnings=[], errors=[])
```

---

## Orchestrator Service Design (B.4.2)

```python
# Conceptual signature — implementation in B.4.2

async def build_manifest_context(
    db: AsyncSession, placement_id: UUID, current_user: User
) -> OrchestratorContext:
    """Resolve full placement → surface → device chain."""

async def resolve_placement_targets(
    db: AsyncSession, placement_id: UUID
) -> list[PlacementTarget]: ...

async def resolve_surface_device_chain(
    db: AsyncSession, targets: list[PlacementTarget]
) -> list[DeviceSurfaceChain]: ...

def check_capability_compatibility(
    context: OrchestratorContext
) -> list[str]: ...

def select_adapter(
    channel_code: str, adapters: dict[str, AdapterContract]
) -> AdapterContract: ...

async def build_adapter_payload(
    context: OrchestratorContext, adapter: AdapterContract
) -> dict: ...
```

---

## Simulation Design (B.4.3)

Simulation — **dry-run only**. Проверяет readiness без записи в БД.

```python
async def simulate_publication(
    db: AsyncSession, placement_id: UUID, current_user: User
) -> SimulationResult:
    """
    Dry-run check:
    1. Placement exists + status valid
    2. channel_id NOT NULL
    3. Targets exist
    4. Each target resolves to surface/carrier
    5. Each surface → logical_carrier → physical_device
    6. Each physical_device → capability_profile
    7. Adapter supports(channel_code, capability_profile)
    8. Payload valid per adapter.validate_payload()
    Returns: ok, warnings[], errors[]
    Does NOT: write to DB, generate manifest, send to devices.
    """
```

### SimulationResult
```python
@dataclass
class SimulationResult:
    ok: bool
    warnings: list[str]   # e.g., "no creative bound"
    errors: list[str]     # e.g., "channel not found", "adapter unsupported"
    context: OrchestratorContext | None = None
```

---

## API Decision

**B.4 без публичного API.**

| Decision | Reasoning |
|---|---|
| No API in B.4.0–B.4.4 | Orchestrator — internal service layer |
| Future: `POST /api/orchestrator/simulate` | After B.4.4 closure, with separate approval |
| Portal: no placement simulation UI | Deferred to after B.5 |

---

## DB/Migration Decision

**B.4 без миграций.**

| Item | Decision |
|---|---|
| `manifest_versions` | Deferred to B.5 |
| `adapter_payloads` | Deferred to B.5 |
| `manifest_targets` | Deferred to B.5 |
| `orchestrator_runs` | Deferred (maybe never — simulation is ephemeral) |

B.4 uses only existing tables: `placements`, `placement_targets`, `display_surfaces`, `logical_carriers`, `physical_devices`, `device_types`, `channels`, `capability_profiles`.

---

## Security/RBAC/RLS Design

### Scope inheritance
```
User → advertiser scope
  └─ Campaign.advertiser_id
       └─ Placement.campaign_id
            └─ Orchestrator inherits scope via Placement→Campaign
```

### Rules
- Orchestrator functions: `resolve_user_scope_context` + `assert_object_in_advertiser_scope`
- Cross-advertiser simulation → 403
- No device secrets exposed in context/payload
- No public device endpoints
- RBAC bypass: forbidden

### Permission
- Simulation: `campaigns.read` (sufficient for dry-run — no state mutation)
- Future publish: `campaigns.manage` (if ever added)

**Rationale:** Simulation is read-only — `campaigns.read` is the least privilege that still enforces advertiser scope.

---

## Audit Design

| Phase | Audit | Decision |
|---|---|---|
| B.4.0–B.4.3 | No audit | No API, ephemeral simulation only |
| B.4.4+ | If simulation API added | `orchestrator.simulation.run` |

### Future audit event (not for B.4)
```
action: "orchestrator.simulation.run"
target_type: "placement"
target_ref: placement_code
details: {warnings_count, errors_count, channel_code, surface_count}
```

---

## Test Strategy

### B.4.1 tests (contracts + mock adapter)
- mock adapter registered ✅
- unsupported channel rejected ✅
- validate_payload on mock returns empty ✅
- simulate_delivery returns ok ✅

### B.4.2 tests (orchestrator service)
- placement without targets → error
- placement without channel_id → error
- target resolves surface → device chain
- capability profile fetched
- adapter selected by channel_code

### B.4.3 tests (simulation)
- full simulation dry-run → ok
- no generated_manifests rows created
- cross-advertiser simulation → 403
- publication flow unchanged
- campaign_targets, kso_placements preserved
- no DROP/TRUNCATE

---

## Risks and Mitigations

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Orchestrator accidentally writes to generated_manifests | HIGH | Simulation only; no DB write methods |
| 2 | Adapter payload leaks device secrets | HIGH | `FORBIDDEN_RESPONSE_KEYS` pattern from manifests |
| 3 | KSO legacy model used instead of universal Placement | MEDIUM | Orchestrator uses Placement (channels/models.py) |
| 4 | Simulation becomes real publish | MEDIUM | Dry-run flag mandatory; no status changes |
| 5 | RLS bypass through orchestrator | HIGH | Scope inheritance from Placement→Campaign |
| 6 | Adapter contract too KSO-specific | MEDIUM | Channel-agnostic by design; mock adapter validates |
| 7 | Manifest generation prematurely integrated | LOW | Deferred to B.5; orchestrator only builds context |

---

## What B.4 Must Not Touch

- ❌ Publication flow (publications/)
- ❌ generated_manifests table/FK
- ❌ kso_placements (legacy)
- ❌ kso_devices
- ❌ campaign_targets
- ❌ Campaign submit validation
- ❌ Placement API (7 endpoints)
- ❌ Device Gateway
- ❌ DROP/TRUNCATE/DELETE
- ❌ Docker/.env

---

## Recommended B.4 Implementation Split

| Step | Content | DB | API | Tests |
|---|---|---|---|---|
| **B.4.1** | `contracts.py` + `mock_adapter.py` | No | No | 4 |
| **B.4.2** | `orchestrator/service.py` — context + chain resolution | No | No | 5 |
| **B.4.3** | `orchestrator/simulation.py` — dry-run engine | No | No | 7 |
| **B.4.4** | Documentation + closure gate | No | No | regression |

**Total: ~16 tests, 0 migrations, 0 API endpoints.**

---

## GO/NO-GO for B.4.1

**✅ GO — B.4.1 AdapterContract + MockAdapter**

Design gate complete. Architecture boundaries defined. All risks identified with mitigations. Implementation strategy: 4 small steps, no DB changes, no API.
