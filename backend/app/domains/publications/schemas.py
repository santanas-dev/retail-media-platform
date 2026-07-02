"""Manifest & Publication Core: Pydantic schemas."""

from datetime import date, datetime, time
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums (string-based for readability) ──────────────────────────

class PublicationBatchStatus:
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    MANIFEST_GENERATED = "manifest_generated"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Valid transitions ────────────────────────────────────────────
# draft → pending_approval, cancelled
# pending_approval → approved, rejected, cancelled
# approved → manifest_generated, cancelled
# manifest_generated → published, cancelled
# published → (terminal, idempotent)
# rejected → (terminal)
# failed → cancelled (retry via new batch)
# cancelled → (terminal)

_VALID_BATCH_TRANSITIONS: dict[str, frozenset[str]] = {
    PublicationBatchStatus.DRAFT: frozenset({
        PublicationBatchStatus.PENDING_APPROVAL,
        PublicationBatchStatus.CANCELLED,
    }),
    PublicationBatchStatus.PENDING_APPROVAL: frozenset({
        PublicationBatchStatus.APPROVED,
        PublicationBatchStatus.REJECTED,
        PublicationBatchStatus.CANCELLED,
    }),
    PublicationBatchStatus.APPROVED: frozenset({
        PublicationBatchStatus.MANIFEST_GENERATED,
        PublicationBatchStatus.CANCELLED,
    }),
    PublicationBatchStatus.MANIFEST_GENERATED: frozenset({
        PublicationBatchStatus.PUBLISHED,
        PublicationBatchStatus.CANCELLED,
    }),
    PublicationBatchStatus.PUBLISHED: frozenset(),
    PublicationBatchStatus.REJECTED: frozenset(),
    PublicationBatchStatus.FAILED: frozenset({
        PublicationBatchStatus.CANCELLED,
    }),
    PublicationBatchStatus.CANCELLED: frozenset(),
}


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


class PublishBatchResult(BaseModel):
    """BACKEND.1.1 — wrapped publish response with feature-flag metadata."""
    batch: PublicationBatchResponse
    generated_manifest_created: bool = False
    next_step: str = "generated_manifest_write_disabled"


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
