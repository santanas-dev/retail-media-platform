"""Emergency Management schemas — Pydantic v2 models.

G.1: contracts only. No API, no migrations, no DB writes.
All actions default to dry_run=True. Real stop disabled.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class EmergencyActionType(str, Enum):
    """Types of emergency actions."""
    STOP_CAMPAIGN = "stop_campaign"
    STOP_PLACEMENT = "stop_placement"
    STOP_CHANNEL = "stop_channel"
    STOP_STORE = "stop_store"
    STOP_DEVICE = "stop_device"
    EMERGENCY_MESSAGE = "emergency_message"
    RESUME = "resume"


class EmergencyActionStatus(str, Enum):
    """Lifecycle statuses for emergency actions."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    COMPLETED = "completed"


class EmergencyPriority(str, Enum):
    """Severity levels for emergency actions."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ═══════════════════════════════════════════════════════════════════════════
# Target
# ═══════════════════════════════════════════════════════════════════════════

class EmergencyTarget(BaseModel):
    """Scope of an emergency action — at least one dimension required."""
    channel_id: Optional[UUID] = None
    channel_code: Optional[str] = Field(default=None, max_length=64)
    store_id: Optional[UUID] = None
    store_code: Optional[str] = Field(default=None, max_length=64)
    physical_device_id: Optional[UUID] = None
    gateway_device_id: Optional[UUID] = None
    device_code: Optional[str] = Field(default=None, max_length=64)
    campaign_id: Optional[UUID] = None
    campaign_code: Optional[str] = Field(default=None, max_length=64)
    placement_id: Optional[UUID] = None
    placement_code: Optional[str] = Field(default=None, max_length=64)
    display_surface_id: Optional[UUID] = None

    @property
    def is_empty(self) -> bool:
        """True if no target dimension is specified."""
        return not any([
            self.channel_id, self.channel_code,
            self.store_id, self.store_code,
            self.physical_device_id, self.gateway_device_id, self.device_code,
            self.campaign_id, self.campaign_code,
            self.placement_id, self.placement_code,
            self.display_surface_id,
        ])

    @property
    def is_broad(self) -> bool:
        """True if target scope is broad (channel or store level, no specific device/campaign)."""
        has_broad = bool(self.channel_id or self.channel_code or self.store_id or self.store_code)
        has_specific = bool(
            self.physical_device_id or self.gateway_device_id or self.device_code or
            self.campaign_id or self.campaign_code or
            self.placement_id or self.placement_code or
            self.display_surface_id
        )
        return has_broad and not has_specific

    @property
    def affected_dimensions(self) -> list[str]:
        """List of affected dimension names."""
        dims: list[str] = []
        if self.channel_id or self.channel_code:
            dims.append("channel")
        if self.store_id or self.store_code:
            dims.append("store")
        if self.physical_device_id or self.gateway_device_id or self.device_code:
            dims.append("device")
        if self.campaign_id or self.campaign_code:
            dims.append("campaign")
        if self.placement_id or self.placement_code:
            dims.append("placement")
        if self.display_surface_id:
            dims.append("display_surface")
        return dims


# ═══════════════════════════════════════════════════════════════════════════
# Message content
# ═══════════════════════════════════════════════════════════════════════════

class EmergencyMessageContent(BaseModel):
    """Content of an emergency broadcast message (plain text only)."""
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=2048)
    media_ref: Optional[str] = Field(default=None, max_length=512)
    media_type: Optional[str] = Field(default=None, max_length=64)
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    severity: Optional[str] = Field(default=None, max_length=32)
    language: Optional[str] = Field(default="ru", max_length=8)


# ═══════════════════════════════════════════════════════════════════════════
# Create request
# ═══════════════════════════════════════════════════════════════════════════

class EmergencyActionCreate(BaseModel):
    """Request to create/preview an emergency action."""
    action_type: EmergencyActionType
    priority: EmergencyPriority = EmergencyPriority.NORMAL
    reason: str = Field(min_length=1, max_length=1024)
    target: EmergencyTarget = Field(default_factory=EmergencyTarget)
    message: Optional[EmergencyMessageContent] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    requires_approval: bool = True
    dry_run: bool = True

    @model_validator(mode="after")
    def _validate_consistency(self):
        # Emergency message requires message content
        if self.action_type == EmergencyActionType.EMERGENCY_MESSAGE:
            if self.message is None:
                raise ValueError("emergency_message action requires message content")

        # Stop actions do NOT require message content
        # (no validation needed — message is optional)

        # Date range
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("starts_at must be <= ends_at")

        # Target must not be empty
        if self.target.is_empty:
            raise ValueError("target must specify at least one dimension")

        # dry_run false is forbidden in G.1
        if not self.dry_run:
            raise ValueError("dry_run=false is not supported in G.1 — real execution is disabled")

        return self


# ═══════════════════════════════════════════════════════════════════════════
# Results
# ═══════════════════════════════════════════════════════════════════════════

class EmergencyIssue(BaseModel):
    """Structured warning/error for emergency operations."""
    code: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(min_length=1, max_length=512)
    field: Optional[str] = Field(default=None, max_length=128)
    details: Optional[dict] = None


class EmergencyActionPreview(BaseModel):
    """Dry-run preview of an emergency action."""
    ok: bool = True
    dry_run: bool = True
    action_type: EmergencyActionType
    target: EmergencyTarget = Field(default_factory=EmergencyTarget)
    affected_channels: int = 0
    affected_stores: int = 0
    affected_devices: int = 0
    affected_campaigns: int = 0
    affected_placements: int = 0
    warnings: list[EmergencyIssue] = Field(default_factory=list)
    errors: list[EmergencyIssue] = Field(default_factory=list)


class EmergencyActionResult(BaseModel):
    """Result of an emergency action (dry-run or real)."""
    ok: bool = True
    action_id: Optional[str] = Field(default=None, max_length=128)
    status: EmergencyActionStatus = EmergencyActionStatus.DRAFT
    dry_run: bool = True
    action_type: EmergencyActionType
    target: EmergencyTarget = Field(default_factory=EmergencyTarget)
    message: Optional[EmergencyMessageContent] = None
    warnings: list[EmergencyIssue] = Field(default_factory=list)
    errors: list[EmergencyIssue] = Field(default_factory=list)


class EmergencyActionRecord(BaseModel):
    """Historical record of an emergency action."""
    id: Optional[str] = Field(default=None, max_length=128)
    action_type: EmergencyActionType
    status: EmergencyActionStatus = EmergencyActionStatus.DRAFT
    priority: EmergencyPriority = EmergencyPriority.NORMAL
    reason: str = ""
    target: EmergencyTarget = Field(default_factory=EmergencyTarget)
    created_by: Optional[str] = Field(default=None, max_length=128)
    approved_by: Optional[str] = Field(default=None, max_length=128)
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    dry_run: bool = True
