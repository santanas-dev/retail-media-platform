"""Scheduling domain: ORM models (Step 37.5).

KsoPlacement — minimal placement linking campaign_code, creative_code,
device_code with a time window.  Stable codes are used instead of raw
UUIDs for safe API responses.

ScheduleItem — Phase C (38.12.1): model added to fix ImportError in
_collect_kso_source_items. Table already existed in DB (created by
prior migration), but SQLAlchemy model was missing.
"""

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Integer, String, Time,
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


class ScheduleItem(Base):
    """ScheduleItem — ORM model for schedule_items table.

    Added during Phase C (38.12.1) — the table existed in DB from prior
    migrations but the SQLAlchemy model was missing, causing ImportError
    in _collect_kso_source_items when the KSO channel was matched.
    """

    __tablename__ = "schedule_items"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    schedule_run_id = Column(UUID(as_uuid=True), ForeignKey("schedule_runs.id"), nullable=False)
    booking_item_id = Column(UUID(as_uuid=True), ForeignKey("booking_items.id"), nullable=False)
    inventory_unit_id = Column(UUID(as_uuid=True), ForeignKey("inventory_units.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    campaign_rendition_id = Column(UUID(as_uuid=True), ForeignKey("campaign_renditions.id"), nullable=False)
    rendition_id = Column(UUID(as_uuid=True), ForeignKey("renditions.id"), nullable=False)
    date = Column(Date, nullable=False)
    time_from = Column(Time, nullable=False)
    time_to = Column(Time, nullable=False)
    loop_position = Column(Integer, nullable=False)
    spot_position = Column(Integer, nullable=False)
    spot_duration_seconds = Column(Integer, nullable=False)
    priority = Column(Integer, default=0)
    weight = Column(Integer, default=1)
    status = Column(String(20), nullable=False, default="active")
