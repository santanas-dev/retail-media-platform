"""
D.2 — Planning Service: Availability Calculation.

Read-only calculations on top of InventoryUnit, CapacityRule, BookingItem, CampaignBooking.
Does NOT create bookings or change state.
Does NOT import Device Gateway, publications, generated_manifests, or portal.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.inventory.models import (
    InventoryUnit, CapacityRule, CampaignBooking, BookingItem,
)
from app.domains.planning.schemas import (
    AvailabilityQuery, AvailabilityResult, InventoryUnitAvailability,
    ConflictCheck, ConflictResult, PlanningConflict,
    OccupancyQuery, OccupancyResult,
    PlanningScenario, PlanningIssue,
)

# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

def validate_date_range(d_from: date, d_to: date) -> list[PlanningIssue]:
    """Validate date range: date_from <= date_to."""
    if d_from > d_to:
        return [build_planning_issue(
            "DATE_RANGE_INVALID", "error",
            f"date_from ({d_from}) > date_to ({d_to})",
            field="date_from",
        )]
    return []


def validate_requested_capacity(
    share_of_voice: float | None,
    spots_per_loop: int | None,
) -> list[PlanningIssue]:
    """Validate requested capacity values."""
    issues: list[PlanningIssue] = []
    if share_of_voice is not None and (share_of_voice < 0 or share_of_voice > 100):
        issues.append(build_planning_issue(
            "INVALID_SHARE_OF_VOICE", "error",
            f"share_of_voice ({share_of_voice}) must be 0..100",
            field="requested_share_of_voice",
        ))
    if spots_per_loop is not None and spots_per_loop < 0:
        issues.append(build_planning_issue(
            "INVALID_SPOTS_PER_LOOP", "error",
            f"spots_per_loop ({spots_per_loop}) must be >= 0",
            field="requested_spots_per_loop",
        ))
    return issues


def validate_inventory_scope(query) -> list[PlanningIssue]:
    """Validate that at least one scope selector is provided."""
    has_scope = any([
        getattr(query, "channel_id", None), getattr(query, "store_id", None),
        getattr(query, "display_surface_id", None),
        getattr(query, "logical_carrier_id", None),
        getattr(query, "inventory_unit_id", None),
    ])
    if not has_scope:
        return [build_planning_issue(
            "NO_SCOPE_SELECTOR", "warning",
            "No scope selector provided (channel, store, surface, carrier, or unit)",
        )]
    return []


def build_planning_issue(
    code: str, severity: str, message: str,
    field: str | None = None, details: dict | None = None,
) -> PlanningIssue:
    """Build a structured PlanningIssue."""
    return PlanningIssue(code=code, severity=severity, message=message,
                         field=field, details=details)


# ═══════════════════════════════════════════════════════════════════════════
# Date overlap helper
# ═══════════════════════════════════════════════════════════════════════════

def ranges_overlap(a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
    """Check if two date ranges overlap. Inclusive on both ends."""
    return a_from <= b_to and b_from <= a_to


# ═══════════════════════════════════════════════════════════════════════════
# Booking status filter — which statuses count as consuming inventory
# ═══════════════════════════════════════════════════════════════════════════

_BOOKING_STATUSES_THAT_CONSUME = frozenset({"approved", "active", "published"})


# ═══════════════════════════════════════════════════════════════════════════
# Availability Calculation
# ═══════════════════════════════════════════════════════════════════════════

async def check_availability(
    db: AsyncSession, query: AvailabilityQuery,
) -> AvailabilityResult:
    """Calculate inventory availability for a given scope and date range.

    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []
    warnings: list[PlanningIssue] = []

    # ── Validate inputs ──────────────────────────────────────────────
    issues.extend(validate_date_range(query.date_from, query.date_to))
    issues.extend(validate_requested_capacity(
        query.requested_share_of_voice, query.requested_spots_per_loop,
    ))
    warnings.extend(validate_inventory_scope(query))

    if issues:
        return AvailabilityResult(
            ok=False, available=False, inventory_units=[], conflicts=[],
            occupancy=[], warnings=warnings, errors=issues,
        )

    # ── Build InventoryUnit query ────────────────────────────────────
    conditions = [InventoryUnit.is_sellable == True]
    if query.inventory_unit_id:
        conditions.append(InventoryUnit.id == query.inventory_unit_id)
    if query.channel_id:
        conditions.append(InventoryUnit.channel_id == query.channel_id)
    if query.store_id:
        conditions.append(InventoryUnit.store_id == query.store_id)
    if query.display_surface_id:
        conditions.append(
            InventoryUnit.display_surface_id == query.display_surface_id,
        )
    if query.logical_carrier_id:
        conditions.append(
            InventoryUnit.logical_carrier_id == query.logical_carrier_id,
        )

    result = await db.execute(select(InventoryUnit).where(*conditions))
    units = result.scalars().all()

    if not units:
        warnings.append(build_planning_issue(
            "INVENTORY_NOT_FOUND", "warning",
            "No sellable inventory units found for the given scope",
        ))
        return AvailabilityResult(
            ok=True, available=False, inventory_units=[], conflicts=[],
            occupancy=[], warnings=warnings, errors=[],
        )

    # ── Load existing bookings for these units ───────────────────────
    unit_ids = [u.id for u in units]
    booking_stmt = (
        select(BookingItem, CampaignBooking)
        .join(CampaignBooking, BookingItem.booking_id == CampaignBooking.id)
        .where(
            BookingItem.inventory_unit_id.in_(unit_ids),
            CampaignBooking.status.in_(_BOOKING_STATUSES_THAT_CONSUME),
        )
    )
    booking_result = await db.execute(booking_stmt)
    booking_rows = [(row[0], row[1]) for row in booking_result.all()]

    # ── Calculate availability per unit ──────────────────────────────
    unit_availabilities: list[InventoryUnitAvailability] = []
    conflicts: list[PlanningConflict] = []
    any_available = False

    for unit in units:
        # Capacity rule lookup (use first matching)
        cap_result = await db.execute(
            select(CapacityRule).where(
                CapacityRule.inventory_unit_id == unit.id,
            ).limit(1)
        )
        capacity_rule = cap_result.scalar_one_or_none()

        cap_max_spots = capacity_rule.max_spots_per_loop if capacity_rule else 0
        if capacity_rule is None:
            warnings.append(build_planning_issue(
                "CAPACITY_RULE_MISSING", "warning",
                f"No capacity rule for inventory unit '{unit.code}'",
                details={"inventory_unit_id": str(unit.id)},
            ))

        # Collect overlapping booking items for this unit
        unit_bookings = [
            (bi, cb)
            for bi, cb in booking_rows
            if (bi.inventory_unit_id == unit.id
                and ranges_overlap(query.date_from, query.date_to,
                                    bi.date_from, bi.date_to))
        ]

        booked_sov = sum(
            float(bi.booked_share_of_voice or 0)
            for bi, _cb in unit_bookings
        )
        booked_spots = sum(
            bi.booked_spots_per_loop or 0
            for bi, _cb in unit_bookings
        )

        available_sov = max(0.0, 100.0 - booked_sov)
        available_spots = max(0, int(cap_max_spots) - booked_spots) if capacity_rule else 0

        # Occupancy
        if booked_sov > 0:
            occupancy = round(booked_sov, 1)
        elif capacity_rule and cap_max_spots > 0:
            occupancy = round(booked_spots / cap_max_spots * 100, 1)
        else:
            occupancy = None

        # Conflict detection
        req_sov = query.requested_share_of_voice
        req_spots = query.requested_spots_per_loop

        if req_sov is not None and req_sov > available_sov:
            conflicts.append(PlanningConflict(
                conflict_type="share_of_voice_exceeded",
                severity="error",
                inventory_unit_id=unit.id,
                date_from=query.date_from, date_to=query.date_to,
                message=(
                    f"Requested {req_sov}% SOV exceeds available "
                    f"{available_sov}% (booked: {booked_sov}%)"
                ),
            ))
        if req_spots is not None and capacity_rule and req_spots > available_spots:
            conflicts.append(PlanningConflict(
                conflict_type="capacity_exceeded",
                severity="error",
                inventory_unit_id=unit.id,
                date_from=query.date_from, date_to=query.date_to,
                message=(
                    f"Requested {req_spots} spots exceeds capacity "
                    f"{cap_max_spots} (booked: {booked_spots})"
                ),
            ))

        # Unit is available if no conflicts reference this unit
        unit_available = not any(
            c.inventory_unit_id == unit.id for c in conflicts
        )
        if unit_available:
            any_available = True

        unit_availabilities.append(InventoryUnitAvailability(
            inventory_unit_id=unit.id,
            inventory_unit_code=unit.code,
            channel_id=unit.channel_id,
            store_id=unit.store_id,
            display_surface_id=unit.display_surface_id,
            logical_carrier_id=unit.logical_carrier_id,
            capability_profile_id=unit.capability_profile_id,
            is_sellable=unit.is_sellable,
            available_share_of_voice=available_sov,
            available_spots_per_loop=available_spots,
            occupancy_percent=occupancy,
        ))

    return AvailabilityResult(
        ok=True,
        available=any_available,
        inventory_units=unit_availabilities,
        conflicts=conflicts,
        occupancy=unit_availabilities,
        warnings=warnings,
        errors=[],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Conflict Check (D.3)
# ═══════════════════════════════════════════════════════════════════════════

async def check_conflicts(
    db: AsyncSession, query: ConflictCheck,
) -> ConflictResult:
    """Check for planning conflicts for proposed placement/booking.

    Reuses check_availability() internally — maps ConflictCheck to AvailabilityQuery.
    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []
    warnings: list[PlanningIssue] = []

    # ── Validate inputs ──────────────────────────────────────────────
    issues.extend(validate_date_range(query.date_from, query.date_to))
    issues.extend(validate_requested_capacity(
        query.requested_share_of_voice, query.requested_spots_per_loop,
    ))

    # Resolve placement_id to inventory scope, if provided
    inventory_unit_id = query.inventory_unit_id
    display_surface_id = query.display_surface_id

    if query.placement_id and not inventory_unit_id:
        from app.domains.channels.models import Placement, PlacementTarget
        placement_result = await db.execute(
            select(Placement).where(Placement.id == query.placement_id)
        )
        placement = placement_result.scalar_one_or_none()
        if not placement:
            issues.append(build_planning_issue(
                "PLACEMENT_NOT_FOUND", "error",
                f"Placement '{query.placement_id}' not found",
                field="placement_id",
            ))
        else:
            # Find PlacementTarget → display_surface → inventory
            target_result = await db.execute(
                select(PlacementTarget).where(
                    PlacementTarget.placement_id == placement.id,
                ).limit(1)
            )
            target = target_result.scalar_one_or_none()
            if target and target.display_surface_id:
                display_surface_id = target.display_surface_id
            else:
                warnings.append(build_planning_issue(
                    "PLACEMENT_TARGET_NOT_FOUND", "warning",
                    f"No target with display_surface for placement '{placement.code}'",
                    field="placement_id",
                ))

    # Validate scope
    has_scope = any([inventory_unit_id, display_surface_id])
    if not has_scope:
        issues.append(build_planning_issue(
            "NO_CONFLICT_SCOPE", "error",
            "No scope for conflict check (inventory_unit_id, display_surface_id, or placement with target)",
        ))

    if issues:
        return ConflictResult(
            has_conflict=False, conflicts=[],
            warnings=warnings + [i for i in issues if i.severity == "warning"],
            errors=[i for i in issues if i.severity == "error"],
        )

    # ── Build AvailabilityQuery ──────────────────────────────────────
    # NB: ConflictCheck has no channel_id/store_id/logical_carrier_id —
    #     conflicts are surface/unit scoped.
    avail_query = AvailabilityQuery(
        inventory_unit_id=inventory_unit_id,
        display_surface_id=display_surface_id,
        date_from=query.date_from,
        date_to=query.date_to,
        requested_share_of_voice=query.requested_share_of_voice,
        requested_spots_per_loop=query.requested_spots_per_loop,
        campaign_id=query.campaign_id,
    )

    # ── Reuse availability engine ────────────────────────────────────
    avail_result = await check_availability(db, avail_query)
    warnings.extend(avail_result.warnings)

    # ── Map availability conflicts + enrich with booking refs ────────
    conflicts: list[PlanningConflict] = []

    # Find existing booking refs for each conflict
    unit_ids = set(c.inventory_unit_id for c in avail_result.conflicts
                   if c.inventory_unit_id)
    if unit_ids and avail_result.conflicts:
        booking_stmt = (
            select(BookingItem, CampaignBooking)
            .join(CampaignBooking, BookingItem.booking_id == CampaignBooking.id)
            .where(
                BookingItem.inventory_unit_id.in_(unit_ids),
                CampaignBooking.status.in_(_BOOKING_STATUSES_THAT_CONSUME),
            )
        )
        booking_result = await db.execute(booking_stmt)
        booking_rows = [(row[0], row[1]) for row in booking_result.all()]

        # Enrich each conflict with existing booking refs if overlapping
        for conflict in avail_result.conflicts:
            enriched = PlanningConflict(
                conflict_type=conflict.conflict_type,
                severity=conflict.severity,
                inventory_unit_id=conflict.inventory_unit_id,
                display_surface_id=conflict.display_surface_id,
                date_from=conflict.date_from,
                date_to=conflict.date_to,
                message=conflict.message,
            )
            # Find the first overlapping booking for this unit
            for bi, cb in booking_rows:
                if (bi.inventory_unit_id == conflict.inventory_unit_id
                        and ranges_overlap(query.date_from, query.date_to,
                                            bi.date_from, bi.date_to)):
                    enriched.existing_campaign_id = cb.campaign_id
                    enriched.existing_booking_id = bi.booking_id
                    enriched.existing_booking_item_id = bi.id
                    break
            conflicts.append(enriched)

    has_conflict = len(conflicts) > 0

    return ConflictResult(
        has_conflict=has_conflict,
        conflicts=conflicts,
        warnings=warnings,
        errors=avail_result.errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Occupancy Calculation (skeleton — D.4 expands)
# ═══════════════════════════════════════════════════════════════════════════

async def calculate_occupancy(
    db: AsyncSession, query: OccupancyQuery,
) -> OccupancyResult:
    """Calculate occupancy for given scope and date range."""
    issues: list[PlanningIssue] = []
    issues.extend(validate_date_range(query.date_from, query.date_to))
    return OccupancyResult(
        date_from=query.date_from, date_to=query.date_to,
        occupancy_percent=0.0,
        warnings=[i for i in issues if i.severity == "warning"],
        errors=[i for i in issues if i.severity == "error"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Planning Scenario (skeleton — D.5 expands)
# ═══════════════════════════════════════════════════════════════════════════

async def simulate_planning_scenario(
    db: AsyncSession, scenario: PlanningScenario,
) -> PlanningScenario:
    """Simulate a planning scenario (dry-run)."""
    issues: list[PlanningIssue] = []
    if scenario.query.date_from > scenario.query.date_to:
        issues.append(build_planning_issue(
            "DATE_RANGE_INVALID", "error",
            "date_from > date_to", field="date_from",
        ))
    scenario.dry_run = True
    scenario.errors = issues
    return scenario


# ═══════════════════════════════════════════════════════════════════════════
# Placement → AvailabilityQuery mapping (skeleton — D.5 expands)
# ═══════════════════════════════════════════════════════════════════════════

async def map_placement_to_availability_query(
    db: AsyncSession, placement_id: UUID,
) -> AvailabilityQuery:
    """Map a Placement to an AvailabilityQuery."""
    return AvailabilityQuery(date_from=date.today(), date_to=date.today())
