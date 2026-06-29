"""
Channels & Devices domain: ORM models.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# Late import to resolve cross-domain relationships
# Placement.campaign references campaigns.models.Campaign
# which must be registered before Placement mapper initializes.
import app.domains.campaigns.models as _campaigns_models  # noqa: F401
import app.domains.organization.models as _org_models  # noqa: F401 — for Store


class Channel(Base):
    """Digital signage channel (канал)."""

    __tablename__ = "channels"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    device_types = relationship("DeviceType", back_populates="channel", lazy="selectin")


class DeviceType(Base):
    """Type of device within a channel (тип устройства)."""

    __tablename__ = "device_types"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "code"),
    )

    channel = relationship("Channel", back_populates="device_types")
    capability_profiles = relationship(
        "CapabilityProfile", back_populates="device_type", lazy="selectin"
    )
    physical_devices = relationship(
        "PhysicalDevice", back_populates="device_type", lazy="selectin"
    )


class CapabilityProfile(Base):
    """Display capabilities for a device type (профиль возможностей)."""

    __tablename__ = "capability_profiles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    device_type_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resolution = Column(String(20))
    orientation = Column(String(20), server_default="landscape")
    formats_json = Column(JSONB)
    max_file_size = Column(BigInteger)
    max_duration = Column(Integer)
    interactive = Column(Boolean, server_default=func.text("false"))
    proof_type = Column(String(50), nullable=False)
    cache_policy = Column(String(50), server_default="full")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    device_type = relationship("DeviceType", back_populates="capability_profiles")
    display_surfaces = relationship(
        "DisplaySurface", back_populates="capability_profile", lazy="selectin"
    )


class PhysicalDevice(Base):
    """Physical device instance (физическое устройство)."""

    __tablename__ = "physical_devices"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_type_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    serial_number = Column(String(255))
    hw_fingerprint = Column(String(512))
    external_code = Column(String(64), unique=True)
    device_properties = Column(JSONB)
    status = Column(String(50), server_default="offline")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    device_type = relationship("DeviceType", back_populates="physical_devices")
    logical_carriers = relationship(
        "LogicalCarrier", back_populates="physical_device", lazy="selectin"
    )


class LogicalCarrier(Base):
    """Logical screen zone on a physical device (логический носитель)."""

    __tablename__ = "logical_carriers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    physical_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("physical_devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type = Column(String(50), nullable=False)
    zone = Column(String(100))
    position = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    physical_device = relationship("PhysicalDevice", back_populates="logical_carriers")
    display_surfaces = relationship(
        "DisplaySurface", back_populates="logical_carrier", lazy="selectin"
    )


class DisplaySurface(Base):
    """Rendered display area on a logical carrier (поверхность показа)."""

    __tablename__ = "display_surfaces"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    logical_carrier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    capability_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resolution = Column(String(20))
    is_active = Column(Boolean, server_default=func.text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    logical_carrier = relationship("LogicalCarrier", back_populates="display_surfaces")
    capability_profile = relationship(
        "CapabilityProfile", back_populates="display_surfaces"
    )


# ──────────────────────────────────────────────────────────────────────────────
# B.3.1 — Placement & PlacementTarget (universal placement entity)
# ──────────────────────────────────────────────────────────────────────────────

class Placement(Base):
    """Universal placement entity (размещение рекламы).

    Links a Campaign to a Channel with optional date range and status.
    Campaign 1→N Placements.
    """

    __tablename__ = "placements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    placement_code = Column(String(64), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, server_default="draft")
    priority = Column(Integer, nullable=False, server_default=func.text("0"))
    start_date = Column(Date)
    end_date = Column(Date)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    campaign = relationship("Campaign", back_populates="placements")
    channel = relationship("Channel")
    targets = relationship(
        "PlacementTarget", back_populates="placement", lazy="selectin",
        cascade="all, delete-orphan",
    )
    # proof_events relationship deferred until ProofEvent ORM model exists (phase C/F)
    # The DB FK proof_events.placement_id → placements.id is already in place.


class PlacementTarget(Base):
    """Target specification for a placement (цель размещения).

    Maps a placement to a store, display surface, or logical carrier.
    Replaces campaign_targets for new placement-based workflows.
    """

    __tablename__ = "placement_targets"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    placement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type = Column(String(20), nullable=False)
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
    )
    display_surface_id = Column(
        UUID(as_uuid=True),
        ForeignKey("display_surfaces.id", ondelete="SET NULL"),
    )
    logical_carrier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("logical_carriers.id", ondelete="SET NULL"),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    placement = relationship("Placement", back_populates="targets")
    store = relationship("Store")
    display_surface = relationship("DisplaySurface")
    logical_carrier = relationship("LogicalCarrier")
