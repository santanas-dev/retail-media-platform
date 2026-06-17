"""Campaigns Core domain: Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


CURRENCY_PATTERN = r"^[A-Z]{3}$"
TARGET_TYPES = frozenset({
    "all_stores", "branch", "cluster", "store",
    "logical_carrier", "display_surface",
})


# ── Campaign ──────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    order_id: UUID
    advertiser_id: UUID | None = None       # auto-populated from order
    brand_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    objective: str | None = Field(None, max_length=100)
    planned_start_date: date
    planned_end_date: date
    priority: int = Field(default=0, ge=0)
    budget: float | None = Field(None, ge=0)
    currency: str = Field(default="RUB", pattern=CURRENCY_PATTERN)
    comment: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "CampaignCreate":
        if self.planned_start_date > self.planned_end_date:
            raise ValueError("planned_start_date must be <= planned_end_date")
        return self


class CampaignUpdate(BaseModel):
    """Only allowed for draft/rejected campaigns."""
    name: str | None = Field(None, min_length=1, max_length=255)
    objective: str | None = Field(None, max_length=100)
    priority: int | None = Field(None, ge=0)
    budget: float | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern=CURRENCY_PATTERN)
    comment: str | None = None


class CampaignResponse(BaseModel):
    id: UUID
    order_id: UUID
    advertiser_id: UUID
    brand_id: UUID | None
    name: str
    objective: str | None
    status: str
    planned_start_date: date
    planned_end_date: date
    priority: int
    budget: float | None
    currency: str
    comment: str | None
    created_by: UUID
    approved_by: UUID | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── CampaignChannel ───────────────────────────────────────────────────────

class CampaignChannelPut(BaseModel):
    channel_ids: list[UUID] = Field(min_length=1)


class CampaignChannelResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    channel_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── CampaignTarget ────────────────────────────────────────────────────────

class CampaignTargetItem(BaseModel):
    target_type: str = Field(pattern=r"^(all_stores|branch|cluster|store|logical_carrier|display_surface)$")
    branch_id: UUID | None = None
    cluster_id: UUID | None = None
    store_id: UUID | None = None
    logical_carrier_id: UUID | None = None
    display_surface_id: UUID | None = None

    @model_validator(mode="after")
    def validate_exclusive_target(self) -> "CampaignTargetItem":
        ids = {
            "branch_id": self.branch_id,
            "cluster_id": self.cluster_id,
            "store_id": self.store_id,
            "logical_carrier_id": self.logical_carrier_id,
            "display_surface_id": self.display_surface_id,
        }
        if self.target_type == "all_stores":
            filled = [k for k, v in ids.items() if v is not None]
            if filled:
                raise ValueError(f"all_stores must have no target id fields, got: {filled}")
            return self
        expected_key = self.target_type + "_id"
        if ids[expected_key] is None:
            raise ValueError(f"target_type={self.target_type} requires {expected_key}")
        del ids[expected_key]
        unexpected = [k for k, v in ids.items() if v is not None]
        if unexpected:
            raise ValueError(
                f"target_type={self.target_type} only allows {expected_key}, "
                f"but also got: {unexpected}"
            )
        return self


class CampaignTargetPut(BaseModel):
    targets: list[CampaignTargetItem]


class CampaignTargetResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    target_type: str
    branch_id: UUID | None
    cluster_id: UUID | None
    store_id: UUID | None
    logical_carrier_id: UUID | None
    display_surface_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── CampaignRendition ─────────────────────────────────────────────────────

class CampaignRenditionItem(BaseModel):
    rendition_id: UUID
    weight: int = Field(default=1, ge=1)
    position: int | None = Field(None, ge=0)


class CampaignRenditionPut(BaseModel):
    renditions: list[CampaignRenditionItem]


class CampaignRenditionResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    rendition_id: UUID
    weight: int
    position: int | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lifecycle ─────────────────────────────────────────────────────────────

class RejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1)
