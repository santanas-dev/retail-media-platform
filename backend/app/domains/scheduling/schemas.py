"""Scheduling Core: Pydantic schemas."""

from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
#  Schedule Run
# ═══════════════════════════════════════════════════════════════════════


class ScheduleRunCreate(BaseModel):
    """Create a new schedule run for a confirmed booking."""

    booking_id: UUID
    comment: Optional[str] = None


class ScheduleRunResponse(BaseModel):
    id: UUID
    booking_id: UUID
    campaign_id: UUID
    status: str
    created_by: UUID
    generated_by: Optional[UUID] = None
    generated_at: Optional[datetime] = None
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Schedule Item
# ═══════════════════════════════════════════════════════════════════════


class ScheduleItemResponse(BaseModel):
    id: UUID
    schedule_run_id: UUID
    booking_item_id: UUID
    inventory_unit_id: UUID
    campaign_id: UUID
    campaign_rendition_id: UUID
    rendition_id: UUID
    date: date
    time_from: time
    time_to: time
    loop_position: int
    spot_position: int
    spot_duration_seconds: int
    priority: int = 0
    weight: int = 1
    status: str = "active"
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Schedule Conflict
# ═══════════════════════════════════════════════════════════════════════


class ScheduleConflictResponse(BaseModel):
    id: UUID
    schedule_run_id: UUID
    inventory_unit_id: Optional[UUID] = None
    booking_item_id: Optional[UUID] = None
    conflict_type: str
    severity: str
    message: str
    details_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Availability / Query params
# ═══════════════════════════════════════════════════════════════════════


class ScheduleItemFilter(BaseModel):
    """Filters for listing schedule items."""

    date_from: Optional[date] = None
    date_to: Optional[date] = None
    inventory_unit_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
