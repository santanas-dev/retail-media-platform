"""Scheduling domain: Pydantic schemas (Step 37.5)."""

from datetime import datetime

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
