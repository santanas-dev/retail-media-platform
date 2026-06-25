"""Scheduling domain: Pydantic schemas (Step 37.5)."""

from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


PLACEMENT_CODE_PATTERN = r"^[a-z0-9_-]+$"


class KsoPlacementCreate(BaseModel):
    """Minimal placement input for test KSO technical validation.

    Links campaign_code → creative_code → device_code in a time window.
    """
    placement_code: str = Field(
        min_length=3, max_length=64, pattern=PLACEMENT_CODE_PATTERN,
    )
    campaign_code: str = Field(min_length=1, max_length=64)
    creative_code: str = Field(min_length=1, max_length=64)
    device_code: str = Field(min_length=1, max_length=64)
    starts_at: datetime
    ends_at: datetime
    slot_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_time_window(self) -> "KsoPlacementCreate":
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class KsoPlacementResponse(BaseModel):
    """Safe read-only view of a KsoPlacement.

    Never exposes: id, created_by, campaign_id, creative_id, device_id,
    store_id, file_path, sha256, storage_ref, minio, backend_url, tokens.
    """
    placement_code: str
    campaign_code: str
    creative_code: str
    device_code: str
    status: str
    starts_at: datetime
    ends_at: datetime
    slot_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class KsoPlacementUpdate(BaseModel):
    """Fields allowed for update — only mutable fields."""
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    slot_order: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_time_window(self) -> "KsoPlacementUpdate":
        if self.starts_at is not None and self.ends_at is not None:
            if self.starts_at >= self.ends_at:
                raise ValueError("starts_at must be before ends_at")
        return self


# ═══════════════════════════════════════════════════════════════════════════
# Schedule + ScheduleSlot schemas (production API 39.1.3)
# ═══════════════════════════════════════════════════════════════════════════

SCHEDULE_CODE_PATTERN = PLACEMENT_CODE_PATTERN


class ScheduleCreate(BaseModel):
    schedule_code: str = Field(min_length=3, max_length=64, pattern=SCHEDULE_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    campaign_code: str | None = Field(None, min_length=1, max_length=64)
    valid_from: date
    valid_to: date
    timezone: str = Field(default="Europe/Moscow", max_length=50)

    @model_validator(mode="after")
    def validate_dates(self) -> "ScheduleCreate":
        if self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class ScheduleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    valid_from: date | None = None
    valid_to: date | None = None
    timezone: str | None = Field(None, max_length=50)


class ScheduleResponse(BaseModel):
    """Safe schedule — no raw UUIDs."""
    schedule_code: str
    name: str
    status: str
    campaign_code: str | None = None
    valid_from: date
    valid_to: date
    timezone: str
    slot_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScheduleSlotCreate(BaseModel):
    slot_code: str = Field(min_length=3, max_length=64, pattern=SCHEDULE_CODE_PATTERN)
    placement_code: str | None = Field(None, min_length=1, max_length=64)
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    slot_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_time(self) -> "ScheduleSlotCreate":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleSlotUpdate(BaseModel):
    placement_code: str | None = Field(None, min_length=1, max_length=64)
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    slot_order: int | None = Field(None, ge=0)


class ScheduleSlotResponse(BaseModel):
    """Safe slot — no raw UUIDs."""
    slot_code: str
    schedule_code: str
    placement_code: str | None = None
    day_of_week: int
    start_time: time
    end_time: time
    slot_order: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
