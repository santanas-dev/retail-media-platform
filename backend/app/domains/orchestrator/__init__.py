"""Channel Orchestrator domain — B.4.

Orchestrates placement → surface → device chain resolution,
adapter selection, payload building, and dry-run simulation.
"""
from app.domains.orchestrator.contracts import (
    AdapterContract,
    AdapterPayloadDraft,
    AdapterSimulationResult,
    DeviceInfo,
    OrchestratorContext,
    SurfaceInfo,
)

__all__ = [
    "AdapterContract",
    "AdapterPayloadDraft",
    "AdapterSimulationResult",
    "DeviceInfo",
    "OrchestratorContext",
    "SurfaceInfo",
]
