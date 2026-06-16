"""Media Library domain: Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Creative ──────────────────────────────────────────────────────────────

class CreativeCreate(BaseModel):
    advertiser_id: UUID
    brand_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    comment: str | None = None


class CreativeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = Field(
        None, pattern=r"^(draft|in_review|approved|rejected|archived)$"
    )
    comment: str | None = None


class CreativeResponse(BaseModel):
    id: UUID
    advertiser_id: UUID
    brand_id: UUID | None
    name: str
    status: str
    comment: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── CreativeVersion ───────────────────────────────────────────────────────

class CreativeVersionResponse(BaseModel):
    id: UUID
    creative_id: UUID
    version: int
    original_filename: str
    file_path: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    uploaded_by: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadVersionResponse(BaseModel):
    creative_id: UUID
    version_id: UUID
    version: int
    original_filename: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None


# ── Rendition ─────────────────────────────────────────────────────────────

class RenditionCreate(BaseModel):
    creative_version_id: UUID
    channel_id: UUID
    capability_profile_id: UUID | None = None


class RenditionResponse(BaseModel):
    id: UUID
    creative_version_id: UUID
    channel_id: UUID
    capability_profile_id: UUID | None
    file_path: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── RenditionValidation ───────────────────────────────────────────────────

class ValidationResponse(BaseModel):
    id: UUID
    rendition_id: UUID
    check_type: str
    result: str
    details_json: dict
    checked_by: UUID
    checked_at: datetime

    model_config = {"from_attributes": True}
