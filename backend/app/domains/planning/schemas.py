"""
D.1 — Planning Pydantic Schemas & Contracts.

Pydantic v2 models for Inventory/Planning service layer.
No ORM models. No DB migrations. No API endpoints.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# Planning Issue — structured error/warning/info
# ═══════════════════════════════════════════════════════════════════════════

class PlanningIssue(BaseModel):
    """Structured planning issue (error / warning / info)."""
    code: str
    severity: str = Field(default="info", pattern=r"^(info|warning|error)$")
    message: str
    field: Optional[str] = None
    details: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════
# Availability
# ═══════════════════════════════════════════════════════════════════════════

class AvailabilityQuery(BaseModel):
    """Query: what inventory is available for given scope + date range?"""
    channel_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    inventory_unit_id: Optional[UUID] = None
    date_from: date
    date_to: date
    target_type: Optional[str] = None
    requested_share_of_voice: Optional[float] = Field(default=None, ge=0, le=100)
    requested_spots_per_loop: Optional[int] = Field(default=None, ge=0)
    advertiser_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None

    @model_validator(mode="after")
    def check_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class InventoryUnitAvailability(BaseModel):
    """Per-unit availability details."""
    inventory_unit_id: UUID
    inventory_unit_code: str
    channel_id: UUID
    store_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    capability_profile_id: Optional[UUID] = None
    is_sellable: bool = True
    available_share_of_voice: Optional[float] = None
    available_spots_per_loop: Optional[int] = None
    occupancy_percent: Optional[float] = None


class AvailabilityResult(BaseModel):
    """Result: availability check outcome."""
    ok: bool = True
    available: bool = False
    inventory_units: list[InventoryUnitAvailability] = Field(default_factory=list)
    conflicts: list = Field(default_factory=list)
    occupancy: list = Field(default_factory=list)
    warnings: list[PlanningIssue] = Field(default_factory=list)
    errors: list[PlanningIssue] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Conflict
# ═══════════════════════════════════════════════════════════════════════════

class ConflictCheck(BaseModel):
    """Query: do proposed parameters conflict with existing bookings?"""
    campaign_id: Optional[UUID] = None
    placement_id: Optional[UUID] = None
    inventory_unit_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    date_from: date
    date_to: date
    requested_share_of_voice: Optional[float] = Field(default=None, ge=0, le=100)
    requested_spots_per_loop: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class PlanningConflict(BaseModel):
    """A single conflict detection result."""
    conflict_type: str
    severity: str = "warning"
    inventory_unit_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    existing_campaign_id: Optional[UUID] = None
    existing_booking_id: Optional[UUID] = None
    existing_booking_item_id: Optional[UUID] = None
    date_from: date
    date_to: date
    message: str


class ConflictResult(BaseModel):
    """Result: conflict check outcome."""
    has_conflict: bool = False
    conflicts: list[PlanningConflict] = Field(default_factory=list)
    warnings: list[PlanningIssue] = Field(default_factory=list)
    errors: list[PlanningIssue] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Occupancy
# ═══════════════════════════════════════════════════════════════════════════

class OccupancyQuery(BaseModel):
    """Query: what's the occupancy for given scope + date range?"""
    inventory_unit_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    date_from: date
    date_to: date
    granularity: Optional[str] = Field(default="day", pattern=r"^(day|hour)$")

    @model_validator(mode="after")
    def check_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class OccupancyResult(BaseModel):
    """Result: occupancy calculation outcome."""
    inventory_unit_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    date_from: date
    date_to: date
    occupancy_percent: float = 0.0
    booked_share_of_voice: Optional[float] = None
    booked_spots_per_loop: Optional[int] = None
    capacity_spots_per_loop: Optional[int] = None
    warnings: list[PlanningIssue] = Field(default_factory=list)
    errors: list[PlanningIssue] = Field(default_factory=list)
    buckets: Optional[list["OccupancyBucket"]] = None
    units: Optional[list["OccupancyUnitBreakdown"]] = None


class OccupancyBucket(BaseModel):
    """Single day occupancy bucket."""
    date: date
    occupancy_percent: float = 0.0
    booked_share_of_voice: Optional[float] = None
    booked_spots_per_loop: Optional[int] = None
    capacity_spots_per_loop: Optional[int] = None


class OccupancyUnitBreakdown(BaseModel):
    """Per-unit occupancy breakdown."""
    inventory_unit_id: UUID
    inventory_unit_code: Optional[str] = None
    occupancy_percent: float = 0.0
    booked_share_of_voice: Optional[float] = None
    booked_spots_per_loop: Optional[int] = None
    capacity_spots_per_loop: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════
# Scenario
# ═══════════════════════════════════════════════════════════════════════════

class PlanningScenario(BaseModel):
    """Planning scenario (dry-run: 'what if?')."""
    scenario_id: Optional[str] = None
    campaign_id: Optional[UUID] = None
    placement_id: Optional[UUID] = None
    query: AvailabilityQuery
    dry_run: bool = True
    availability_result: Optional[AvailabilityResult] = None
    conflict_result: Optional[ConflictResult] = None
    occupancy_result: Optional[OccupancyResult] = None
    warnings: list[PlanningIssue] = Field(default_factory=list)
    errors: list[PlanningIssue] = Field(default_factory=list)
