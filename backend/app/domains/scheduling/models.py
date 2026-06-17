"""Scheduling Core: SQLAlchemy ORM models."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ScheduleRun(Base):
    """A schedule generation run for a confirmed booking."""

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

    # Relationships
    items = relationship(
        "ScheduleItem", back_populates="schedule_run",
        lazy="selectin", order_by="ScheduleItem.date, ScheduleItem.loop_position, ScheduleItem.spot_position",
    )
    conflicts = relationship(
        "ScheduleConflict", back_populates="schedule_run",
        lazy="selectin",
    )


class ScheduleItem(Base):
    """A single placement slot in a schedule."""

    __tablename__ = "schedule_items"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    schedule_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    booking_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("booking_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_unit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaign_renditions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("renditions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    date = Column(Date, nullable=False)
    time_from = Column(Time, nullable=False)
    time_to = Column(Time, nullable=False)
    loop_position = Column(Integer, nullable=False)
    spot_position = Column(Integer, nullable=False)
    spot_duration_seconds = Column(Integer, nullable=False)
    priority = Column(Integer, server_default=func.text("0"))
    weight = Column(Integer, server_default=func.text("1"))
    status = Column(
        String(20), nullable=False, server_default="active",
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    schedule_run = relationship("ScheduleRun", back_populates="items")


class ScheduleConflict(Base):
    """A problem detected during schedule generation."""

    __tablename__ = "schedule_conflicts"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    schedule_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    inventory_unit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_units.id", ondelete="RESTRICT"),
        nullable=True,
    )
    booking_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("booking_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    conflict_type = Column(String(50), nullable=False)
    severity = Column(
        String(20), nullable=False, server_default="error",
    )
    message = Column(Text, nullable=False)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    schedule_run = relationship("ScheduleRun", back_populates="conflicts")
