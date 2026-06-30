"""
D.1 — Planning Service Contracts.

Skeleton functions without business logic.
Does NOT:
- create CampaignBooking / BookingItem
- change Placement / Campaign
- write generated_manifests
- call Device Gateway / Orchestrator delivery
- do real publish
"""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.planning.schemas import (
    AvailabilityQuery,
    AvailabilityResult,
    ConflictCheck,
    ConflictResult,
    OccupancyQuery,
    OccupancyResult,
    PlanningScenario,
    PlanningIssue,
)


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

def validate_date_range(date_from: date, date_to: date) -> list[PlanningIssue]:
    """Validate date range: date_from <= date_to."""
    if date_from > date_to:
        return [build_planning_issue(
            "DATE_RANGE_INVALID", "error",
            f"date_from ({date_from}) > date_to ({date_to})",
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
        query.channel_id,
        query.store_id,
        query.display_surface_id,
        query.logical_carrier_id,
        query.inventory_unit_id,
    ])
    if not has_scope:
        return [build_planning_issue(
            "NO_SCOPE_SELECTOR", "warning",
            "No scope selector provided (channel, store, surface, carrier, or unit)",
        )]
    return []


def build_planning_issue(
    code: str,
    severity: str,
    message: str,
    field: str | None = None,
    details: dict | None = None,
) -> PlanningIssue:
    """Build a structured PlanningIssue."""
    return PlanningIssue(
        code=code,
        severity=severity,
        message=message,
        field=field,
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Service contracts (skeleton — no business logic yet)
# ═══════════════════════════════════════════════════════════════════════════

async def check_availability(
    db: AsyncSession,
    query: AvailabilityQuery,
) -> AvailabilityResult:
    """Check inventory availability for given scope and date range.

    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []

    # Validate inputs
    issues.extend(validate_date_range(query.date_from, query.date_to))
    issues.extend(validate_requested_capacity(
        query.requested_share_of_voice,
        query.requested_spots_per_loop,
    ))
    issues.extend(validate_inventory_scope(query))

    # Future: read InventoryUnit + CapacityRule + BookingItem
    # Future: calculate available capacity
    # Future: detect conflicts with existing bookings

    return AvailabilityResult(
        ok=len(issues) == 0,
        available=False,  # not computed yet
        inventory_units=[],
        conflicts=[],
        occupancy=[],
        warnings=[i for i in issues if i.severity == "warning"],
        errors=[i for i in issues if i.severity == "error"],
    )


async def check_conflicts(
    db: AsyncSession,
    query: ConflictCheck,
) -> ConflictResult:
    """Check for planning conflicts for proposed placement/booking.

    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []

    issues.extend(validate_date_range(query.date_from, query.date_to))
    issues.extend(validate_requested_capacity(
        query.requested_share_of_voice,
        query.requested_spots_per_loop,
    ))

    # Future: check date overlap with existing bookings
    # Future: check capacity conflicts per inventory_unit

    return ConflictResult(
        has_conflict=False,
        conflicts=[],
        warnings=[i for i in issues if i.severity == "warning"],
        errors=[i for i in issues if i.severity == "error"],
    )


async def calculate_occupancy(
    db: AsyncSession,
    query: OccupancyQuery,
) -> OccupancyResult:
    """Calculate occupancy for given scope and date range.

    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []

    issues.extend(validate_date_range(query.date_from, query.date_to))

    # Future: read BookingItems for the scope
    # Future: compute booked_share_of_voice / booked_spots
    # Future: compute occupancy_percent

    return OccupancyResult(
        date_from=query.date_from,
        date_to=query.date_to,
        occupancy_percent=0.0,
        warnings=[i for i in issues if i.severity == "warning"],
        errors=[i for i in issues if i.severity == "error"],
    )


async def simulate_planning_scenario(
    db: AsyncSession,
    scenario: PlanningScenario,
) -> PlanningScenario:
    """Simulate a planning scenario (dry-run).

    Does NOT create bookings or change state.
    """
    issues: list[PlanningIssue] = []

    if scenario.query.date_from > scenario.query.date_to:
        issues.append(build_planning_issue(
            "DATE_RANGE_INVALID", "error",
            "date_from > date_to",
            field="date_from",
        ))

    # Future: run check_availability + check_conflicts + calculate_occupancy
    # Future: compose results

    scenario.dry_run = True
    scenario.errors = issues
    return scenario


async def map_placement_to_availability_query(
    db: AsyncSession,
    placement_id: UUID,
) -> AvailabilityQuery:
    """Map a Placement to an AvailabilityQuery for the same scope/dates.

    Does NOT create bookings or change state.
    """
    # Future: load Placement + PlacementTargets
    # Future: derive date_from/date_to from campaign.planned_start/end
    # Future: derive channel_id, display_surface_id from targets

    # For now: return a minimal query — caller handles "placement not found"
    return AvailabilityQuery(
        date_from=date.today(),
        date_to=date.today(),
    )
