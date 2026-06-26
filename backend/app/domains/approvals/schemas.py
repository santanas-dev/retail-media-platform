"""Approvals domain: Pydantic schemas (Step 37.6)."""

from datetime import datetime

from pydantic import BaseModel, Field


APPROVAL_CODE_PATTERN = r"^[a-z0-9_-]+$"


class ApprovalRequestCreate(BaseModel):
    """Request approval for a campaign, placement, or publication_batch."""
    object_type: str = Field(pattern=r"^(campaign|placement|publication_batch)$")
    object_code: str = Field(min_length=1, max_length=64)
    comment: str | None = Field(None, max_length=500)


class ApprovalDecide(BaseModel):
    """Decide on an approval request (approve/reject)."""
    decision: str = Field(pattern=r"^(approve|reject)$")
    comment: str | None = Field(None, max_length=500)


class ApprovalResponse(BaseModel):
    """Safe read-only view of an approval request.

    Never exposes: id, requested_by, decided_by, backend_url, tokens.
    """
    approval_code: str
    object_type: str
    object_code: str
    status: str
    decision: str | None = None
    comment: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None

    model_config = {"from_attributes": True}
