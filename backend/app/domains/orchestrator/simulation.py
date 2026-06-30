"""
B.4.3 — Orchestrator Simulation Engine.

Dry-run simulation of placement publication — resolves chain,
selects adapter, builds payload, validates, assembles draft.
No DB writes. No API. No real publish. No generated_manifests.
"""
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.orchestrator.service import (
    build_manifest_context,
    check_capability_compatibility,
    select_adapter,
    build_adapter_payload,
    assemble_manifest_draft,
    ManifestDraft,
    # Error types
    PlacementNotFound,
    PlacementHasNoChannel,
    PlacementHasNoTargets,
    SurfaceChainIncomplete,
    CapabilityMismatch,
    UnsupportedChannel,
    AdapterValidationFailed,
)


# ═══════════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SimulationError:
    """Structured error from a simulation step."""
    step: str
    code: str
    message: str
    detail: str | None = None


@dataclass
class SimulationResult:
    """Full dry-run simulation result for one placement.

    Contains context, adapter info, payload preview, warnings, errors.
    Never exposes: device secrets, tokens, credentials, generated_manifests IDs.
    """
    placement_id: str
    placement_code: str
    campaign_id: str | None = None
    channel_code: str | None = None
    ok: bool = False
    dry_run: bool = True
    target_count: int = 0
    surface_count: int = 0
    device_count: int = 0
    adapter_name: str | None = None
    payload_preview: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[SimulationError] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationSummary:
    """Aggregate summary across multiple placement simulations."""
    total: int = 0
    ok: int = 0
    failed: int = 0
    warnings: int = 0
    errors: int = 0
    results: list[SimulationResult] = field(default_factory=list)
    channel_codes: set[str] = field(default_factory=set)


# ═══════════════════════════════════════════════════════════════════════════
# Simulation engine
# ═══════════════════════════════════════════════════════════════════════════

async def simulate_placement(
    db: AsyncSession,
    placement_id: UUID,
    current_user: User | None = None,
) -> SimulationResult:
    """Full dry-run simulation for a single placement.

    Flow:
    1. Build manifest context (resolve chain + RLS)
    2. Check capability compatibility
    3. Select adapter by channel_code
    4. Build adapter payload draft
    5. Validate payload
    6. Assemble manifest draft

    Returns structured SimulationResult with ok/warnings/errors.
    Does NOT write to DB. Does NOT generate manifests. Does NOT publish.
    """
    warnings: list[str] = []
    errors: list[SimulationError] = []

    # ── Step 1: Build context (resolve chain) ──────────────────────────
    try:
        context = await build_manifest_context(db, placement_id, current_user)
    except PlacementNotFound as e:
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code="unknown",
            ok=False,
            errors=[SimulationError(
                step="resolve_context", code="placement_not_found",
                message=e.detail,
            )],
        )
    except PlacementHasNoChannel as e:
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code="unknown",
            ok=False,
            errors=[SimulationError(
                step="resolve_context", code="placement_no_channel",
                message=e.detail,
            )],
        )
    except PlacementHasNoTargets as e:
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code="unknown",
            ok=False,
            errors=[SimulationError(
                step="resolve_context", code="placement_no_targets",
                message=e.detail,
            )],
        )
    except HTTPException as e:
        # RLS denial (403) or other HTTP errors during chain resolution
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code="unknown",
            ok=False,
            errors=[SimulationError(
                step="resolve_context", code="access_denied",
                message=str(e.detail) if hasattr(e, 'detail') else str(e),
                detail=str(e.status_code),
            )],
        )

    # Track chain warnings
    if context.devices:
        for device in context.devices:
            for surface in device.surfaces:
                if not surface.proof_type:
                    warnings.append(
                        f"Surface {surface.surface_id}: no proof_type"
                    )

    # ── Step 2: Capability compatibility ───────────────────────────────
    cap_errors = check_capability_compatibility(context)
    if cap_errors:
        errors.append(SimulationError(
            step="capability_check", code="capability_mismatch",
            message="; ".join(cap_errors),
        ))

    # ── Step 3: Select adapter ─────────────────────────────────────────
    adapter_name: str | None = None
    try:
        adapter = select_adapter(context.channel_code)
        adapter_name = adapter.adapter_name
    except UnsupportedChannel as e:
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code=context.placement_code,
            campaign_id=context.campaign_id,
            channel_code=context.channel_code,
            ok=False,
            dry_run=True,
            target_count=sum(1 for d in context.devices),  # rough proxy
            surface_count=sum(len(d.surfaces) for d in context.devices),
            device_count=len(context.devices),
            warnings=warnings,
            errors=[SimulationError(
                step="select_adapter", code="unsupported_channel",
                message=e.detail,
            )],
        )

    # ── Step 4: Build adapter payload ──────────────────────────────────
    try:
        payload = await build_adapter_payload(context, adapter)
    except Exception as e:
        return SimulationResult(
            placement_id=str(placement_id),
            placement_code=context.placement_code,
            campaign_id=context.campaign_id,
            channel_code=context.channel_code,
            ok=False,
            dry_run=True,
            target_count=sum(1 for d in context.devices),
            surface_count=sum(len(d.surfaces) for d in context.devices),
            device_count=len(context.devices),
            adapter_name=adapter_name,
            warnings=warnings,
            errors=[SimulationError(
                step="build_payload", code="payload_build_failed",
                message=str(e),
            )],
        )

    # ── Step 5: Validate payload ───────────────────────────────────────
    validation_errors = adapter.validate_payload(payload.payload)
    if validation_errors:
        errors.append(SimulationError(
            step="validate_payload", code="adapter_validation_failed",
            message="; ".join(validation_errors),
        ))

    # ── Step 6: Assemble draft ─────────────────────────────────────────
    try:
        draft = assemble_manifest_draft(context, payload)
        # Merge draft warnings/errors
        warnings.extend(draft.warnings)
        for draft_err in draft.errors:
            errors.append(SimulationError(
                step="assemble_draft", code="draft_error",
                message=draft_err,
            ))
    except Exception as e:
        errors.append(SimulationError(
            step="assemble_draft", code="draft_assembly_failed",
            message=str(e),
        ))

    # ── Build result ───────────────────────────────────────────────────
    ok = len(errors) == 0

    # Safe payload preview — never expose raw payload with potential secrets
    payload_preview = {
        "adapter": payload.adapter_name,
        "channel": payload.channel_code,
        "keys": list(payload.payload.keys()) if payload.payload else [],
    }

    return SimulationResult(
        placement_id=str(placement_id),
        placement_code=context.placement_code,
        campaign_id=context.campaign_id,
        channel_code=context.channel_code,
        ok=ok,
        dry_run=True,
        target_count=sum(1 for d in context.devices),
        surface_count=sum(len(d.surfaces) for d in context.devices),
        device_count=len(context.devices),
        adapter_name=adapter_name,
        payload_preview=payload_preview,
        warnings=warnings,
        errors=errors,
        details={
            "devices": [
                {
                    "device_code": d.device_code,
                    "surfaces": [s.surface_id for s in d.surfaces],
                }
                for d in context.devices
            ],
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Batch simulation
# ═══════════════════════════════════════════════════════════════════════════

async def simulate_placements(
    db: AsyncSession,
    placement_ids: list[UUID],
    current_user: User | None = None,
) -> list[SimulationResult]:
    """Run dry-run simulation for multiple placements.

    Each placement is simulated independently. Errors in one
    placement do not stop simulation of others.
    """
    results: list[SimulationResult] = []
    for pid in placement_ids:
        result = await simulate_placement(db, pid, current_user)
        results.append(result)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

def summarize_simulation_results(
    results: list[SimulationResult],
) -> SimulationSummary:
    """Aggregate simulation results into a summary."""
    summary = SimulationSummary(total=len(results))
    channel_codes: set[str] = set()

    for r in results:
        if r.ok:
            summary.ok += 1
        else:
            summary.failed += 1
        summary.warnings += len(r.warnings)
        summary.errors += len(r.errors)
        if r.channel_code:
            channel_codes.add(r.channel_code)

    summary.results = results
    summary.channel_codes = channel_codes
    return summary
