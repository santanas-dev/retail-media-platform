"""
D.5.1 — Planning API: read-only / dry-run endpoints.

5 endpoints built on top of planning service functions (D.1–D.4).
All endpoints are read-only — no CampaignBooking/BookingItem creation.
RLS: advertiser scope via campaign_id/placement_id; store scope via store_id.
Audit: planning.{availability,conflict,occupancy,scenario}.{checked,viewed,simulated}
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import (
    resolve_user_scope_context,
    assert_object_in_advertiser_scope,
)
from app.domains.audit.service import audit_business_action
from app.domains.planning import schemas, service

router = APIRouter(prefix="/api/planning", tags=["planning"])


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _ensure_advertiser_scope(
    db: AsyncSession,
    current_user: identity_models.User,
    campaign_id: UUID | None = None,
    placement_id: UUID | None = None,
) -> None:
    """Enforce advertiser scope for planning operations.

    If campaign_id is provided: load campaign → get advertiser_id → check scope.
    If placement_id is provided: load placement → campaign → advertiser_id → check scope.
    Uses direct DB lookups — no service/router dependency.
    """
    advertiser_id: UUID | None = None

    if campaign_id:
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(Campaign.advertiser_id).where(Campaign.id == campaign_id)
        )
        advertiser_id = result.scalar_one_or_none()

    elif placement_id:
        from app.domains.channels.models import Placement
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(Placement.campaign_id).where(Placement.id == placement_id)
        )
        campaign_id_found = result.scalar_one_or_none()
        if campaign_id_found:
            camp_result = await db.execute(
                sa_select(Campaign.advertiser_id).where(
                    Campaign.id == campaign_id_found
                )
            )
            advertiser_id = camp_result.scalar_one_or_none()

    if advertiser_id is not None:
        ctx = await resolve_user_scope_context(db, current_user)
        assert_object_in_advertiser_scope(advertiser_id, ctx)


async def _audit_planning(
    db: AsyncSession,
    current_user: identity_models.User,
    action: str,
    campaign_id: UUID | None = None,
    placement_id: UUID | None = None,
    inventory_unit_id: UUID | None = None,
    store_id: UUID | None = None,
    channel_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    result_summary: str = "",
) -> None:
    """Fire-and-forget audit for planning actions."""
    details: dict = {
        "result_summary": result_summary,
    }
    if campaign_id:
        details["campaign_id"] = str(campaign_id)
    if placement_id:
        details["placement_id"] = str(placement_id)
    if inventory_unit_id:
        details["inventory_unit_id"] = str(inventory_unit_id)
    if store_id:
        details["store_id"] = str(store_id)
    if channel_id:
        details["channel_id"] = str(channel_id)
    if date_from:
        details["date_from"] = date_from.isoformat()
    if date_to:
        details["date_to"] = date_to.isoformat()

    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action=action, target_type="planning",
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Availability
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/availability", response_model=schemas.AvailabilityResult)
async def planning_availability(
    channel_id: UUID | None = Query(None),
    store_id: UUID | None = Query(None),
    display_surface_id: UUID | None = Query(None),
    logical_carrier_id: UUID | None = Query(None),
    inventory_unit_id: UUID | None = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    requested_share_of_voice: float | None = Query(None, ge=0, le=100),
    requested_spots_per_loop: int | None = Query(None, ge=0),
    campaign_id: UUID | None = Query(None),
    placement_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("planning.read")
    ),
):
    """Check inventory availability for given scope and date range (read-only)."""
    await _ensure_advertiser_scope(
        db, current_user, campaign_id=campaign_id, placement_id=placement_id,
    )

    try:
        query = schemas.AvailabilityQuery(
            channel_id=channel_id,
            store_id=store_id,
            display_surface_id=display_surface_id,
            logical_carrier_id=logical_carrier_id,
            inventory_unit_id=inventory_unit_id,
            date_from=date_from,
            date_to=date_to,
            requested_share_of_voice=requested_share_of_voice,
            requested_spots_per_loop=requested_spots_per_loop,
            campaign_id=campaign_id,
        )
    except ValueError as exc:
        from fastapi import HTTPException as HTTPEx
        raise HTTPEx(status_code=422, detail=str(exc))
    result = await service.check_availability(db, query)

    await _audit_planning(
        db, current_user,
        action="planning.availability.checked",
        campaign_id=campaign_id, placement_id=placement_id,
        inventory_unit_id=inventory_unit_id, store_id=store_id,
        channel_id=channel_id, date_from=date_from, date_to=date_to,
        result_summary=f"available={result.available}, units={len(result.inventory_units)}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. Conflict Check
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/check-conflicts", response_model=schemas.ConflictResult)
async def planning_check_conflicts(
    data: schemas.ConflictCheck,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("planning.read")
    ),
):
    """Check for planning conflicts (read-only, no booking creation)."""
    await _ensure_advertiser_scope(
        db, current_user,
        campaign_id=data.campaign_id,
        placement_id=data.placement_id,
    )

    result = await service.check_conflicts(db, data)

    await _audit_planning(
        db, current_user,
        action="planning.conflict.checked",
        campaign_id=data.campaign_id, placement_id=data.placement_id,
        inventory_unit_id=data.inventory_unit_id,
        date_from=data.date_from, date_to=data.date_to,
        result_summary=f"has_conflict={result.has_conflict}, conflicts={len(result.conflicts)}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 3. Occupancy
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/occupancy", response_model=schemas.OccupancyResult)
async def planning_occupancy(
    inventory_unit_id: UUID | None = Query(None),
    display_surface_id: UUID | None = Query(None),
    channel_id: UUID | None = Query(None),
    store_id: UUID | None = Query(None),
    logical_carrier_id: UUID | None = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    granularity: str | None = Query("day", pattern=r"^(day|hour)$"),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("planning.read")
    ),
):
    """Calculate occupancy for given scope and date range (read-only)."""
    # Store scope enforcement if store_id is provided
    if store_id:
        ctx = await resolve_user_scope_context(db, current_user)
        from app.domains.identity.rls import assert_object_in_store_scope
        assert_object_in_store_scope(store_id, ctx)

    query = schemas.OccupancyQuery(
        inventory_unit_id=inventory_unit_id,
        display_surface_id=display_surface_id,
        channel_id=channel_id,
        store_id=store_id,
        logical_carrier_id=logical_carrier_id,
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
    )
    result = await service.calculate_occupancy(db, query)

    await _audit_planning(
        db, current_user,
        action="planning.occupancy.viewed",
        inventory_unit_id=inventory_unit_id, store_id=store_id,
        channel_id=channel_id,
        date_from=date_from, date_to=date_to,
        result_summary=f"occupancy={result.occupancy_percent}%",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 4. Scenario Simulation
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/scenario", response_model=schemas.PlanningScenario)
async def planning_scenario(
    data: schemas.PlanningScenario,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("planning.read")
    ),
):
    """Simulate a planning scenario (dry-run only)."""
    await _ensure_advertiser_scope(
        db, current_user,
        campaign_id=data.campaign_id,
        placement_id=data.placement_id,
    )

    # Ensure dry-run is always true
    data.dry_run = True
    result = await service.simulate_planning_scenario(db, data)

    await _audit_planning(
        db, current_user,
        action="planning.scenario.simulated",
        campaign_id=data.campaign_id, placement_id=data.placement_id,
        result_summary=f"dry_run={result.dry_run}, errors={len(result.errors)}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5. Inventory Units Availability (convenience)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/inventory-units/availability",
    response_model=schemas.AvailabilityResult,
)
async def planning_inventory_units_availability(
    channel_id: UUID | None = Query(None),
    store_id: UUID | None = Query(None),
    display_surface_id: UUID | None = Query(None),
    logical_carrier_id: UUID | None = Query(None),
    inventory_unit_id: UUID | None = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    requested_share_of_voice: float | None = Query(None, ge=0, le=100),
    requested_spots_per_loop: int | None = Query(None, ge=0),
    campaign_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("planning.read")
    ),
):
    """Convenience endpoint: availability filtered by inventory units (read-only)."""
    await _ensure_advertiser_scope(
        db, current_user, campaign_id=campaign_id,
    )

    query = schemas.AvailabilityQuery(
        channel_id=channel_id,
        store_id=store_id,
        display_surface_id=display_surface_id,
        logical_carrier_id=logical_carrier_id,
        inventory_unit_id=inventory_unit_id,
        date_from=date_from,
        date_to=date_to,
        requested_share_of_voice=requested_share_of_voice,
        requested_spots_per_loop=requested_spots_per_loop,
        campaign_id=campaign_id,
    )
    result = await service.check_availability(db, query)

    await _audit_planning(
        db, current_user,
        action="planning.availability.checked",
        campaign_id=campaign_id,
        inventory_unit_id=inventory_unit_id, store_id=store_id,
        channel_id=channel_id, date_from=date_from, date_to=date_to,
        result_summary=f"available={result.available}, units={len(result.inventory_units)}",
    )

    return result
