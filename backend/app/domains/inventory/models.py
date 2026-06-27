"""Inventory & Booking domain: ORM models."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class InventoryUnit(Base):
    """Sellable advertising unit linked to physical infrastructure."""

    __tablename__ = "inventory_units"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    logical_carrier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    display_surface_id = Column(
        UUID(as_uuid=True),
        ForeignKey("display_surfaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    capability_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status = Column(String(32), nullable=False, server_default="active")
    is_sellable = Column(Boolean, nullable=False, server_default=func.text("false"))
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    capacity_rules = relationship(
        "CapacityRule", back_populates="inventory_unit", lazy="selectin",
    )


class CapacityRule(Base):
    """Capacity rule defining ad slots for an inventory unit."""

    __tablename__ = "inventory_capacity_rules"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    inventory_unit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=False)
    days_of_week_json = Column(
        JSONB, nullable=False, server_default=func.text("'[1,2,3,4,5,6,7]'")
    )
    time_from = Column(Time, nullable=False, server_default=func.text("'00:00:00'"))
    time_to = Column(Time, nullable=False, server_default=func.text("'23:59:59'"))
    loop_duration_seconds = Column(Integer, nullable=False)
    spot_duration_seconds = Column(Integer, nullable=False)
    max_spots_per_loop = Column(Integer, nullable=False)
    max_share_of_voice = Column(
        Numeric(5, 4), server_default=func.text("1.0"),
    )
    status = Column(String(32), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    inventory_unit = relationship("InventoryUnit", back_populates="capacity_rules")


class CampaignBooking(Base):
    """Booking — reservation of inventory for a campaign."""

    __tablename__ = "campaign_bookings"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(32), nullable=False, server_default="draft")
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True))
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship(
        "BookingItem", back_populates="booking", lazy="selectin",
        cascade="all, delete-orphan",
    )


class BookingItem(Base):
    """Individual item within a booking — links to an inventory unit."""

    __tablename__ = "booking_items"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_unit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booked_spots_per_loop = Column(Integer, nullable=False)
    booked_share_of_voice = Column(Numeric(5, 4), nullable=True)
    reservation_type = Column(String(20), nullable=False, server_default="campaign")
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("booking_id", "inventory_unit_id", name="uq_bi_booking_unit"),
    )

    booking = relationship("CampaignBooking", back_populates="items")
