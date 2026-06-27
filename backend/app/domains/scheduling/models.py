"""Scheduling domain: ORM models (Step 37.5).

KsoPlacement — minimal placement linking campaign_code, creative_code,
device_code with a time window.  Stable codes are used instead of raw
UUIDs for safe API responses.

ScheduleItem — Phase C (38.12.1): model added to fix ImportError in
_collect_kso_source_items. Table already existed in DB (created by
prior migration), but SQLAlchemy model was missing.
"""

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Integer, String, Time, Boolean, Text,
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


# ═══════════════════════════════════════════════════════════════════════════
# Schedule + ScheduleSlot — production schedule API (39.1.3)
# ═══════════════════════════════════════════════════════════════════════════

class Schedule(Base):
    """Schedule — groups time slots for campaign/placement delivery."""

    __tablename__ = "schedules"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    schedule_code = Column(
        String(64), unique=True, nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    status = Column(
        String(20), nullable=False, server_default="draft", index=True,
    )
    campaign_code = Column(
        String(64),
        ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=False)
    timezone = Column(String(50), nullable=False, server_default="Europe/Moscow")
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

    slots = relationship(
        "ScheduleSlot", back_populates="schedule", lazy="selectin",
        order_by="ScheduleSlot.slot_order",
    )


class ScheduleSlot(Base):
    """ScheduleSlot — daily time slot linked to a placement."""

    __tablename__ = "schedule_slots"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    slot_code = Column(
        String(64), unique=True, nullable=False, index=True,
    )
    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    placement_code = Column(
        String(64),
        ForeignKey("kso_placements.placement_code", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    day_of_week = Column(
        Integer, nullable=False,  # 0=Mon … 6=Sun
    )
    start_time = Column(
        Time, nullable=False,
    )
    end_time = Column(
        Time, nullable=False,
    )
    slot_order = Column(
        Integer, nullable=False, server_default="0",
    )
    is_active = Column(
        Boolean, nullable=False, server_default=func.text("true"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    schedule = relationship("Schedule", back_populates="slots")


# ═══════════════════════════════════════════════════════════════════════════
# ScheduleRun — ORM model for existing schedule_runs table (41.4.1)
# ═══════════════════════════════════════════════════════════════════════════

class ScheduleRun(Base):
    """ScheduleRun — one scheduling run for a campaign+booking pair.

    Table ``schedule_runs`` was created by alembic migration 008 but the
    ORM model was missing.  Added in 41.4.1 to enable the full publication
    batch workflow (generate_manifests).  No migration needed — table
    already exists.
    """

    __tablename__ = "schedule_runs"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(
        String(32), nullable=False, server_default="draft",
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generated_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    generated_at = Column(DateTime(timezone=True))
    approved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True))
    comment = Column(Text)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    items = relationship(
        "ScheduleItem", backref="schedule_run", lazy="selectin",
    )
