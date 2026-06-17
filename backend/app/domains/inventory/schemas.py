"""Inventory & Booking domain: Pydantic schemas."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ── Inventory Unit ─────────────────────────────────────────────────


class InventoryUnitCreate(BaseModel):
    code: str = Field(..., pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    channel_id: UUID
    store_id: UUID
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    capability_profile_id: Optional[UUID] = None
    status: str = "active"
    is_sellable: bool = False
    comment: Optional[str] = None

    @model_validator(mode="after")
    def sellable_requires_surface(self):
        if self.is_sellable and self.logical_carrier_id is None and self.display_surface_id is None:
            raise ValueError(
                "is_sellable=true requires logical_carrier_id or display_surface_id"
            )
        return self


class InventoryUnitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    capability_profile_id: Optional[UUID] = None
    status: Optional[str] = None
    is_sellable: Optional[bool] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def sellable_requires_surface(self):
        if self.is_sellable is True and self.logical_carrier_id is None and self.display_surface_id is None:
            raise ValueError(
                "is_sellable=true requires logical_carrier_id or display_surface_id"
            )
        return self


class InventoryUnitResponse(BaseModel):
    id: UUID
    code: str
    name: str
    channel_id: UUID
    store_id: UUID
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    capability_profile_id: Optional[UUID] = None
    status: str
    is_sellable: bool
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Capacity Rule ──────────────────────────────────────────────────


class CapacityRuleCreate(BaseModel):
    valid_from: date
    valid_to: date
    days_of_week_json: list[int] = Field(default=[1, 2, 3, 4, 5, 6, 7])
    time_from: str = "00:00:00"
    time_to: str = "23:59:59"
    loop_duration_seconds: int = Field(..., gt=0)
    spot_duration_seconds: int = Field(..., gt=0)
    max_spots_per_loop: int = Field(..., gt=0)
    max_share_of_voice: Decimal = Field(default=Decimal("1.0"))
    status: str = "active"

    @model_validator(mode="after")
    def validate_fields(self):
        if self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        if self.time_from >= self.time_to:
            raise ValueError("time_from must be < time_to")
        for d in self.days_of_week_json:
            if d < 1 or d > 7:
                raise ValueError(f"Invalid day_of_week: {d} (must be 1..7)")
        if self.max_share_of_voice <= 0 or self.max_share_of_voice > 1:
            raise ValueError("max_share_of_voice must be > 0 and <= 1")
        return self


class CapacityRuleUpdate(BaseModel):
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    days_of_week_json: Optional[list[int]] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    loop_duration_seconds: Optional[int] = Field(None, gt=0)
    spot_duration_seconds: Optional[int] = Field(None, gt=0)
    max_spots_per_loop: Optional[int] = Field(None, gt=0)
    max_share_of_voice: Optional[Decimal] = None
    status: Optional[str] = None

    @model_validator(mode="after")
    def validate_fields(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        if self.time_from and self.time_to and self.time_from >= self.time_to:
            raise ValueError("time_from must be < time_to")
        if self.days_of_week_json is not None:
            for d in self.days_of_week_json:
                if d < 1 or d > 7:
                    raise ValueError(f"Invalid day_of_week: {d} (must be 1..7)")
        if self.max_share_of_voice is not None:
            if self.max_share_of_voice <= 0 or self.max_share_of_voice > 1:
                raise ValueError("max_share_of_voice must be > 0 and <= 1")
        return self


class CapacityRuleResponse(BaseModel):
    id: UUID
    inventory_unit_id: UUID
    valid_from: date
    valid_to: date
    days_of_week_json: list
    time_from: str
    time_to: str
    loop_duration_seconds: int
    spot_duration_seconds: int
    max_spots_per_loop: int
    max_share_of_voice: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Availability ───────────────────────────────────────────────────


class AvailabilityRequest(BaseModel):
    campaign_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None
    cluster_id: Optional[UUID] = None
    date_from: date
    date_to: date
    inventory_unit_ids: Optional[list[UUID]] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class AvailabilityItem(BaseModel):
    inventory_unit_id: UUID
    inventory_unit_code: str
    capacity_total: int
    confirmed_booked: int
    reserved_booked: int
    available: int
    status: str  # available / limited / unavailable
    reasons: list[str] = []


class AvailabilityResponse(BaseModel):
    items: list[AvailabilityItem]


# ── Booking ────────────────────────────────────────────────────────


class BookingCreate(BaseModel):
    campaign_id: UUID
    date_from: date
    date_to: date
    comment: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class BookingUpdate(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    comment: Optional[str] = None


class BookingResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    status: str
    date_from: date
    date_to: date
    created_by: UUID
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Booking Item ───────────────────────────────────────────────────


class BookingItemRequest(BaseModel):
    inventory_unit_id: UUID
    booked_spots_per_loop: int = Field(..., gt=0)
    booked_share_of_voice: Optional[Decimal] = None
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def validate_fields(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        if self.booked_share_of_voice is not None:
            if self.booked_share_of_voice <= 0 or self.booked_share_of_voice > 1:
                raise ValueError("booked_share_of_voice must be > 0 and <= 1")
        return self


class BookingItemsUpdate(BaseModel):
    items: list[BookingItemRequest]


class BookingItemResponse(BaseModel):
    id: UUID
    booking_id: UUID
    inventory_unit_id: UUID
    booked_spots_per_loop: int
    booked_share_of_voice: Optional[Decimal] = None
    date_from: date
    date_to: date
    created_at: datetime

    model_config = {"from_attributes": True}
