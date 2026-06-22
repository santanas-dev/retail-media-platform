"""Scheduling domain: ORM models (Step 37.5).

KsoPlacement — minimal placement linking campaign_code, creative_code,
device_code with a time window.  Stable codes are used instead of raw
UUIDs for safe API responses.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class KsoPlacement(Base):
    """KsoPlacement — places a campaign+creative on a KSO device in a time window.

    Test KSO vertical slice: minimal placement without inventory planning,
    airtime booking, or commercial scheduling.  Uses stable external codes
    (campaign_code, creative_code, device_code) so API responses never
    expose raw UUIDs.
    """

    __tablename__ = "kso_placements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    placement_code = Column(
        String(64), unique=True, nullable=False, index=True,
    )
    campaign_code = Column(
        String(64),
        ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creative_code = Column(
        String(64),
        ForeignKey("creatives.creative_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_code = Column(
        String(64),
        ForeignKey("kso_devices.device_code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    starts_at = Column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    ends_at = Column(
        DateTime(timezone=True), nullable=False,
    )
    status = Column(
        String(20), nullable=False, server_default="draft", index=True,
    )
    slot_order = Column(
        Integer, nullable=False, server_default="0",
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
