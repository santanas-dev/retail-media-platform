"""Manifest & Publication Core: Pydantic schemas."""

from datetime import date, datetime, time
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums (string-based for readability) ──────────────────────────

class PublicationBatchStatus:
    DRAFT = "draft"
    GENERATED = "generated"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublicationTargetStatus:
    PENDING = "pending"
    GENERATED = "generated"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManifestVersionStatus:
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


# ── PublicationBatch ──────────────────────────────────────────────

class PublicationBatchCreate(BaseModel):
    schedule_run_id: str
    comment: Optional[str] = None
    # campaign_id and booking_id are derived from schedule_run, not accepted


class PublicationBatchResponse(BaseModel):
    id: UUID
    schedule_run_id: UUID
    campaign_id: UUID
    booking_id: UUID
    status: str
    comment: Optional[str] = None
    created_by: UUID
    created_at: datetime
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    published_by: Optional[UUID] = None
    published_at: Optional[datetime] = None
    cancelled_by: Optional[UUID] = None
    cancelled_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PublicationBatchListResponse(BaseModel):
    """Lightweight list item (no nested collections)."""
    id: UUID
    schedule_run_id: UUID
    campaign_id: UUID
    booking_id: UUID
    status: str
    comment: Optional[str] = None
    created_by: UUID
    created_at: datetime
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    published_by: Optional[UUID] = None
    published_at: Optional[datetime] = None
    cancelled_by: Optional[UUID] = None
    cancelled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── PublicationTarget ─────────────────────────────────────────────

class PublicationTargetResponse(BaseModel):
    id: UUID
    publication_batch_id: UUID
    inventory_unit_id: UUID
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    channel_id: UUID
    store_id: UUID
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── ManifestVersion ───────────────────────────────────────────────

class ManifestVersionResponse(BaseModel):
    id: UUID
    publication_batch_id: UUID
    publication_target_id: UUID
    manifest_version: int
    manifest_json: dict[str, Any]
    manifest_hash: str
    signature: Optional[str] = None
    status: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ManifestVersionListResponse(BaseModel):
    """List item — excludes large manifest_json for efficiency."""
    id: UUID
    publication_batch_id: UUID
    publication_target_id: UUID
    manifest_version: int
    manifest_hash: str
    signature: Optional[str] = None
    status: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── ManifestItem ──────────────────────────────────────────────────

class ManifestItemResponse(BaseModel):
    id: UUID
    manifest_version_id: UUID
    schedule_item_id: UUID
    campaign_id: UUID
    campaign_rendition_id: UUID
    rendition_id: UUID
    creative_version_id: UUID
    media_path: str
    sha256: str
    date: date
    time_from: time
    time_to: time
    loop_position: int
    spot_position: int

    model_config = {"from_attributes": True}


# ── PublicationEvent ──────────────────────────────────────────────

class PublicationEventResponse(BaseModel):
    id: UUID
    publication_batch_id: UUID
    event_type: str
    actor_user_id: Optional[UUID] = None
    message: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}
