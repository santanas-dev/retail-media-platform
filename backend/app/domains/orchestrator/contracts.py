"""
B.4.1 — Channel Orchestrator Contracts.

Channel-agnostic AdapterContract + context/payload/result types.
No KSO-specific fields. No DB writes. No device secrets.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Context types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SurfaceInfo:
    """Resolved display surface with capability profile."""
    surface_id: str
    resolution: str | None = None
    orientation: str | None = None
    formats: list[str] = field(default_factory=list)
    max_file_size: int | None = None
    max_duration: int | None = None
    proof_type: str | None = None
    interactive: bool = False


@dataclass
class DeviceInfo:
    """Resolved physical device in the surface chain."""
    device_id: str
    device_code: str | None = None
    store_id: str | None = None
    status: str | None = None
    surfaces: list[SurfaceInfo] = field(default_factory=list)


@dataclass
class OrchestratorContext:
    """Full resolved context for adapter payload building.

    Built by Orchestrator service from Placement → PlacementTarget →
    DisplaySurface → LogicalCarrier → PhysicalDevice chain.
    """
    placement_id: str
    placement_code: str
    campaign_id: str
    channel_code: str
    channel_name: str | None = None
    devices: list[DeviceInfo] = field(default_factory=list)
    creative_codes: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AdapterPayloadDraft:
    """Channel-specific payload draft built by adapter."""
    channel_code: str
    adapter_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AdapterSimulationResult:
    """Dry-run simulation result from adapter."""
    ok: bool
    adapter_name: str
    channel_code: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# AdapterContract (ABC)
# ═══════════════════════════════════════════════════════════════════════════

class AdapterContract(ABC):
    """Channel-agnostic adapter interface.

    Each channel (KSO, Android TV, ESL, ...) implements this contract.
    Orchestrator selects adapter by channel_code and delegates
    payload building + simulation to it.
    """

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Human-readable adapter name (e.g. 'kso', 'android_tv')."""
        ...

    @property
    @abstractmethod
    def channel_code(self) -> str:
        """Channel code this adapter handles (e.g. 'kso', 'android_tv')."""
        ...

    @abstractmethod
    def supports(
        self, channel_code: str, capability_profile: dict[str, Any] | None = None,
    ) -> bool:
        """Check if this adapter supports the given channel + capability profile.

        Args:
            channel_code: target channel code
            capability_profile: optional dict with at least:
                {orientation, resolution, formats, proof_type, interactive, ...}

        Returns:
            True if this adapter can handle this channel/profile combination.
        """
        ...

    @abstractmethod
    async def build_payload(
        self, context: OrchestratorContext,
    ) -> AdapterPayloadDraft:
        """Build channel-specific payload draft from resolved context.

        Does NOT write to DB. Does NOT contact devices.
        """
        ...

    @abstractmethod
    def validate_payload(self, payload: dict[str, Any]) -> list[str]:
        """Validate payload structure. Returns list of error messages.

        Empty list = valid.
        """
        ...

    @abstractmethod
    async def simulate_delivery(
        self, payload: dict[str, Any],
    ) -> AdapterSimulationResult:
        """Dry-run simulation — check delivery feasibility.

        Does NOT send to devices. Does NOT write to DB.
        """
        ...
