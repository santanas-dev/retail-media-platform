"""
B.4.1 — Mock Adapter for Channel Orchestrator.

Implements AdapterContract for testing. Always-compatible.
No DB writes. No device calls. No KSO-specific logic.
"""
from typing import Any

from app.domains.orchestrator.contracts import (
    AdapterContract,
    AdapterPayloadDraft,
    AdapterSimulationResult,
    OrchestratorContext,
)


class MockAdapter(AdapterContract):
    """Always-compatible mock adapter for testing orchestrator flows.

    Supports any channel_code and capability_profile.
    Returns minimal payload draft. Simulation always succeeds.
    """

    adapter_name = "mock"
    channel_code = "mock"

    def supports(
        self, channel_code: str, capability_profile: dict[str, Any] | None = None,
    ) -> bool:
        """Mock adapter supports ONLY channel_code='mock'.

        Returns False for any other channel_code — this ensures
        Orchestrator can detect unsupported channels via registry lookup,
        not via a wildcard adapter that hides errors.
        """
        if not channel_code:
            return False
        return channel_code == self.channel_code

    async def build_payload(
        self, context: OrchestratorContext,
    ) -> AdapterPayloadDraft:
        """Build minimal mock payload from context.

        No DB access. No device communication.
        """
        return AdapterPayloadDraft(
            channel_code=context.channel_code,
            adapter_name=self.adapter_name,
            payload={
                "adapter": "mock",
                "channel": context.channel_code,
                "placement_code": context.placement_code,
                "devices": len(context.devices),
                "surfaces": sum(len(d.surfaces) for d in context.devices),
                "creative_count": len(context.creative_codes),
            },
            warnings=[],
        )

    def validate_payload(self, payload: dict[str, Any]) -> list[str]:
        """Validate mock payload structure.

        Required fields: adapter, channel, placement_code.
        """
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["payload must be a dict"]
        if payload.get("adapter") != "mock":
            errors.append("payload.adapter must be 'mock'")
        if not payload.get("channel"):
            errors.append("payload.channel is required")
        if not payload.get("placement_code"):
            errors.append("payload.placement_code is required")
        return errors

    async def simulate_delivery(
        self, payload: dict[str, Any],
    ) -> AdapterSimulationResult:
        """Mock delivery simulation — always succeeds.

        Returns ok=True with device_count and surface_count details.
        """
        device_count = payload.get("devices", 0)
        surface_count = payload.get("surfaces", 0)
        warnings: list[str] = []
        if device_count == 0:
            warnings.append("No devices in payload")
        if surface_count == 0:
            warnings.append("No surfaces in payload")

        return AdapterSimulationResult(
            ok=True,
            adapter_name=self.adapter_name,
            channel_code=payload.get("channel", "mock"),
            warnings=warnings,
            details={
                "device_count": device_count,
                "surface_count": surface_count,
                "placement_code": payload.get("placement_code", ""),
            },
        )
