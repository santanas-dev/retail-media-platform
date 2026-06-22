"""Approvals domain: ORM models (Step 37.6).

ApprovalRequest — minimal approval for campaign/placement objects.
Uses stable object_code (not raw UUID).  Maker-checker enforced.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# Valid object types that can be approved
VALID_OBJECT_TYPES = frozenset({"campaign", "placement"})

# Valid approval statuses
VALID_APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})

# Valid decisions
VALID_DECISIONS = frozenset({"approve", "reject"})


class ApprovalRequest(Base):
    """ApprovalRequest — minimal approval gate for test KSO vertical slice.

    object_code is a stable external code (campaign_code, placement_code),
    not a raw UUID.  One active pending per object_type+object_code.
    Maker-checker: requested_by != decided_by.
    """

    __tablename__ = "approval_requests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    approval_code = Column(
        String(64), unique=True, nullable=False, index=True,
    )
    object_type = Column(
        String(20), nullable=False,
    )
    object_code = Column(
        String(64), nullable=False,
    )
    status = Column(
        String(20), nullable=False, server_default="pending", index=True,
    )
    requested_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decided_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision = Column(
        String(20), nullable=True,
    )
    comment = Column(
        String(500), nullable=True,
    )
    requested_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    decided_at = Column(
        DateTime(timezone=True), nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
