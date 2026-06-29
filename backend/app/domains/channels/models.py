"""
Channels & Devices domain: ORM models.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
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
