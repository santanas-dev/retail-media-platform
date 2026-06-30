"""
B.4.2 — Orchestrator Service.

Placement → Surface → Device chain resolution.
Adapter selection. Payload building. Manifest draft assembly.

No DB writes. No API. No publication/manifest imports.
No generated_manifests. No kso_placements.
"""
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.channels import models as channel_models
from app.domains.campaigns.models import Campaign
from app.domains.identity.models import User
from app.domains.identity.rls import (
    resolve_user_scope_context,
    assert_object_in_advertiser_scope,
)
from app.domains.orchestrator.contracts import (
    AdapterContract,
    AdapterPayloadDraft,
    AdapterSimulationResult,
    DeviceInfo,
    OrchestratorContext,
    SurfaceInfo,
)
from app.domains.adapters.registry import get_adapter as registry_get_adapter


# ═══════════════════════════════════════════════════════════════════════════
# Error types
# ═══════════════════════════════════════════════════════════════════════════

class OrchestratorError(HTTPException):
    """Base orchestrator error."""
    pass


class PlacementNotFound(OrchestratorError):
    def __init__(self, placement_id: str):
        super().__init__(status_code=404, detail=f"Placement '{placement_id}' not found")


class PlacementHasNoChannel(OrchestratorError):
    def __init__(self, placement_id: str):
        super().__init__(
            status_code=400,
            detail=f"Placement '{placement_id}' has no channel assigned",
        )


class PlacementHasNoTargets(OrchestratorError):
    def __init__(self, placement_id: str):
        super().__init__(
            status_code=400,
            detail=f"Placement '{placement_id}' has no targets",
        )


class SurfaceChainIncomplete(OrchestratorError):
    def __init__(self, surface_id: str, missing: str):
        super().__init__(
            status_code=400,
            detail=f"Surface '{surface_id}': {missing} not found in device chain",
        )


class CapabilityMismatch(OrchestratorError):
    def __init__(self, channel_code: str, reason: str):
        super().__init__(
            status_code=400,
            detail=f"Capability mismatch for channel '{channel_code}': {reason}",
        )


class UnsupportedChannel(OrchestratorError):
    def __init__(self, channel_code: str):
        super().__init__(
            status_code=400,
            detail=f"No adapter registered for channel '{channel_code}'",
        )


class AdapterValidationFailed(OrchestratorError):
    def __init__(self, adapter_name: str, errors: list[str]):
        super().__init__(
            status_code=400,
            detail=f"Adapter '{adapter_name}' validation failed: {'; '.join(errors)}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Context assembly
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ChainResult:
    """Intermediate result from resolving placement → surface → device chain."""
    placement: channel_models.Placement
    campaign: Campaign
    channel: channel_models.Channel
    targets: list[channel_models.PlacementTarget]
    devices: list[DeviceInfo]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def build_manifest_context(
    db: AsyncSession,
    placement_id: UUID,
    current_user: User | None = None,
) -> OrchestratorContext:
    """Build full manifest context from placement → surface → device chain.

    Enforces advertiser scope if current_user is provided.
    """
    # Resolve placement + targets + chain
    chain = await _resolve_chain(db, placement_id, current_user)

    if chain.errors:
        # Return partial context with errors
        return OrchestratorContext(
            placement_id=str(placement_id),
            placement_code=chain.placement.placement_code,
            campaign_id=str(chain.placement.campaign_id),
            channel_code=chain.channel.code,
            channel_name=chain.channel.name,
            devices=chain.devices,
        )

    return OrchestratorContext(
        placement_id=str(chain.placement.id),
        placement_code=chain.placement.placement_code,
        campaign_id=str(chain.campaign.id),
        channel_code=chain.channel.code,
        channel_name=chain.channel.name,
        devices=chain.devices,
        start_date=(
            chain.placement.start_date.isoformat()
            if chain.placement.start_date else None
        ),
        end_date=(
            chain.placement.end_date.isoformat()
            if chain.placement.end_date else None
        ),
    )


async def _resolve_chain(
    db: AsyncSession,
    placement_id: UUID,
    current_user: User | None = None,
) -> ChainResult:
    """Resolve full placement → surface → device chain."""

    # 1. Find placement
    result = await db.execute(
        select(channel_models.Placement).where(
            channel_models.Placement.id == placement_id,
        )
    )
    placement = result.scalar_one_or_none()
    if not placement:
        raise PlacementNotFound(str(placement_id))

    # 2. Check channel_id
    if not placement.channel_id:
        raise PlacementHasNoChannel(str(placement_id))

    # 3. Find campaign (for scope check)
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == placement.campaign_id)
    )
    campaign = camp_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # 4. RLS: advertiser scope
    if current_user is not None:
        scope_ctx = await resolve_user_scope_context(db, current_user)
        assert_object_in_advertiser_scope(
            campaign.advertiser_id, scope_ctx, "resolve placement chain",
        )

    # 5. Find channel
    ch_result = await db.execute(
        select(channel_models.Channel).where(
            channel_models.Channel.id == placement.channel_id,
        )
    )
    channel = ch_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # 6. Resolve targets
    targets = await resolve_placement_targets(db, placement_id)

    # 7. Resolve device chain
    devices, chain_errors = await resolve_surface_device_chain(db, targets)

    return ChainResult(
        placement=placement,
        campaign=campaign,
        channel=channel,
        targets=targets,
        devices=devices,
        errors=chain_errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Target resolution
# ═══════════════════════════════════════════════════════════════════════════

async def resolve_placement_targets(
    db: AsyncSession,
    placement_id: UUID,
) -> list[channel_models.PlacementTarget]:
    """Resolve all targets for a placement.

    Raises PlacementHasNoTargets if zero targets found.
    """
    result = await db.execute(
        select(channel_models.PlacementTarget).where(
            channel_models.PlacementTarget.placement_id == placement_id,
        )
    )
    targets = list(result.scalars().all())
    if not targets:
        raise PlacementHasNoTargets(str(placement_id))
    return targets


# ═══════════════════════════════════════════════════════════════════════════
# Surface → Device chain resolution
# ═══════════════════════════════════════════════════════════════════════════

async def resolve_surface_device_chain(
    db: AsyncSession,
    targets: list[channel_models.PlacementTarget],
) -> tuple[list[DeviceInfo], list[str]]:
    """Resolve display_surface → logical_carrier → physical_device chain.

    Returns (devices, errors).
    Skips targets with target_type='store' (no surface to resolve).
    """
    devices: list[DeviceInfo] = []
    errors: list[str] = []

    # Collect all display_surface_ids
    surface_ids: set[UUID] = set()
    for t in targets:
        if t.target_type == "surface" and t.display_surface_id:
            surface_ids.add(t.display_surface_id)
        elif t.target_type == "carrier" and t.logical_carrier_id:
            # For carrier targets, find surfaces linked to the carrier
            lc_result = await db.execute(
                select(channel_models.DisplaySurface).where(
                    channel_models.DisplaySurface.logical_carrier_id == t.logical_carrier_id,
                )
            )
            for surface in lc_result.scalars().all():
                surface_ids.add(surface.id)

    if not surface_ids:
        errors.append("No display surfaces found for any targets")
        return devices, errors

    # Load all surfaces
    surfaces_result = await db.execute(
        select(channel_models.DisplaySurface).where(
            channel_models.DisplaySurface.id.in_(surface_ids),
        )
    )
    surfaces = list(surfaces_result.scalars().all())

    # Collect carrier_ids and physical_device_ids
    carrier_ids: set[UUID] = set()
    surface_map: dict[UUID, list[channel_models.DisplaySurface]] = {}
    for s in surfaces:
        if s.logical_carrier_id:
            carrier_ids.add(s.logical_carrier_id)
            surface_map.setdefault(s.logical_carrier_id, []).append(s)

    if not carrier_ids:
        errors.append("No logical carriers found for display surfaces")
        return devices, errors

    # Load carriers
    carriers_result = await db.execute(
        select(channel_models.LogicalCarrier).where(
            channel_models.LogicalCarrier.id.in_(carrier_ids),
        )
    )
    carriers = {c.id: c for c in carriers_result.scalars().all()}

    device_ids: set[UUID] = set()
    for c in carriers.values():
        if c.physical_device_id:
            device_ids.add(c.physical_device_id)

    if not device_ids:
        errors.append("No physical devices found for logical carriers")
        return devices, errors

    # Load physical devices
    devices_result = await db.execute(
        select(channel_models.PhysicalDevice).where(
            channel_models.PhysicalDevice.id.in_(device_ids),
        )
    )
    physical_devices = {d.id: d for d in devices_result.scalars().all()}

    # Load device types
    dt_ids = {d.device_type_id for d in physical_devices.values() if d.device_type_id}
    device_types: dict[UUID, channel_models.DeviceType] = {}
    if dt_ids:
        dt_result = await db.execute(
            select(channel_models.DeviceType).where(
                channel_models.DeviceType.id.in_(dt_ids),
            )
        )
        device_types = {dt.id: dt for dt in dt_result.scalars().all()}

    # Load capability profiles
    cp_ids: set[UUID] = set()
    for s in surfaces:
        if s.capability_profile_id:
            cp_ids.add(s.capability_profile_id)
    profiles: dict[UUID, channel_models.CapabilityProfile] = {}
    if cp_ids:
        cp_result = await db.execute(
            select(channel_models.CapabilityProfile).where(
                channel_models.CapabilityProfile.id.in_(cp_ids),
            )
        )
        profiles = {cp.id: cp for cp in cp_result.scalars().all()}

    # Build DeviceInfo list
    for pd_id, pd in physical_devices.items():
        # Find carriers for this device
        device_carriers = [
            c for c in carriers.values() if c.physical_device_id == pd_id
        ]
        device_surfaces: list[SurfaceInfo] = []
        for c in device_carriers:
            for s in surface_map.get(c.id, []):
                cp = profiles.get(s.capability_profile_id) if s.capability_profile_id else None
                device_surfaces.append(SurfaceInfo(
                    surface_id=str(s.id),
                    resolution=s.resolution or (cp.resolution if cp else None),
                    orientation=cp.orientation if cp else None,
                    formats=cp.formats_json if cp and cp.formats_json else [],
                    max_file_size=cp.max_file_size if cp else None,
                    max_duration=cp.max_duration if cp else None,
                    proof_type=cp.proof_type if cp else None,
                    interactive=cp.interactive if cp else False,
                ))

        dt = device_types.get(pd.device_type_id) if pd.device_type_id else None
        devices.append(DeviceInfo(
            device_id=str(pd.id),
            device_code=pd.external_code,
            store_id=str(pd.store_id) if pd.store_id else None,
            status=pd.status,
            surfaces=device_surfaces,
        ))

    return devices, errors


# ═══════════════════════════════════════════════════════════════════════════
# Capability compatibility
# ═══════════════════════════════════════════════════════════════════════════

def check_capability_compatibility(
    context: OrchestratorContext,
) -> list[str]:
    """Check channel/capability compatibility across all devices.

    Returns list of error messages. Empty = compatible.
    """
    errors: list[str] = []
    if not context.devices:
        errors.append("No devices in context")
        return errors

    for device in context.devices:
        for surface in device.surfaces:
            if not surface.orientation:
                errors.append(
                    f"Device {device.device_code or device.device_id}: "
                    "no orientation in surface profile"
                )
            if not surface.formats:
                errors.append(
                    f"Device {device.device_code or device.device_id}: "
                    "no supported formats in surface profile"
                )
    return errors


# ═══════════════════════════════════════════════════════════════════════════
# Adapter selection
# ═══════════════════════════════════════════════════════════════════════════

def select_adapter(channel_code: str) -> AdapterContract:
    """Select adapter by channel_code from registry.

    Raises UnsupportedChannel if no adapter registered.
    """
    adapter = registry_get_adapter(channel_code)
    if adapter is None:
        raise UnsupportedChannel(channel_code)
    if not adapter.supports(channel_code):
        raise UnsupportedChannel(channel_code)
    return adapter


# ═══════════════════════════════════════════════════════════════════════════
# Payload building
# ═══════════════════════════════════════════════════════════════════════════

async def build_adapter_payload(
    context: OrchestratorContext,
    adapter: AdapterContract,
) -> AdapterPayloadDraft:
    """Build channel-specific payload via adapter.

    Does NOT write to DB. Does NOT contact devices.
    """
    return await adapter.build_payload(context)


# ═══════════════════════════════════════════════════════════════════════════
# Manifest draft
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ManifestDraft:
    """Dry-run manifest draft — NOT a signed manifest."""
    placement_code: str
    channel_code: str
    adapter_name: str
    context: dict[str, Any] = field(default_factory=dict)
    adapter_payload: dict[str, Any] = field(default_factory=dict)
    status: str = "dry_run"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def assemble_manifest_draft(
    context: OrchestratorContext,
    payload: AdapterPayloadDraft,
) -> ManifestDraft:
    """Assemble internal manifest draft from context + adapter payload.

    This is NOT a signed manifest. Does NOT write to generated_manifests.
    Does NOT change publication status.
    """
    warnings = list(payload.warnings)
    errors: list[str] = []

    if not context.devices:
        warnings.append("No devices resolved in context")
    if not context.channel_code:
        errors.append("Missing channel_code in context")

    return ManifestDraft(
        placement_code=context.placement_code,
        channel_code=context.channel_code,
        adapter_name=payload.adapter_name,
        context={
            "placement_code": context.placement_code,
            "channel_code": context.channel_code,
            "device_count": len(context.devices),
            "surface_count": sum(len(d.surfaces) for d in context.devices),
        },
        adapter_payload=payload.payload,
        status="dry_run",
        warnings=warnings,
        errors=errors,
    )
