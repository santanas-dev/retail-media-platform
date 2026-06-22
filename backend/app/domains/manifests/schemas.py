"""Manifest schemas — safe responses only."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ManifestGenerateRequest(BaseModel):
    """Generate manifest from approved placement."""
    placement_code: str = Field(..., min_length=1, max_length=64)
    manifest_code: str = Field(..., min_length=1, max_length=64)


class ManifestPublishRequest(BaseModel):
    """Publish a generated manifest."""
    pass  # No payload needed — manifest_code in URL path


class ManifestResponse(BaseModel):
    """Safe manifest response — never exposes IDs, tokens, paths."""
    manifest_code: str
    device_code: str
    placement_code: str
    campaign_code: str
    status: str
    schema_version: int
    item_count: int
    preview_body: Optional[dict[str, Any]] = None
    media_ref_format: Optional[str] = None
    generated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ManifestListItem(BaseModel):
    """List item — excludes large preview_body for efficiency."""
    manifest_code: str
    device_code: str
    placement_code: str
    campaign_code: str
    status: str
    schema_version: int
    item_count: int
    generated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
