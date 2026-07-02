"""
Retail Media Platform — SQLAlchemy ORM Models.

Phase 2: Foundation tables only — organization, channels, devices, surfaces.
No identity/auth, no campaigns, no content, no inventory yet.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

__all__ = [
    "Base",
    "Branch",
    "Cluster",
    "Store",
    "Channel",
    "DeviceType",
    "CapabilityProfile",
    "PhysicalDevice",
    "DeviceCertificate",
    "DeviceStatusHistory",
    "LogicalCarrier",
    "DisplaySurface",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class Branch(Base):
    __tablename__ = "branches"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    timezone = Column(String(64), nullable=False, default="Europe/Moscow")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    clusters = relationship("Cluster", back_populates="branch")


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    branch = relationship("Branch", back_populates="clusters")
    stores = relationship("Store", back_populates="cluster")


class Store(Base):
    __tablename__ = "stores"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    cluster_id = Column(String(36), ForeignKey("clusters.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False, default="")
    timezone = Column(String(64), nullable=False, default="Europe/Moscow")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    cluster = relationship("Cluster", back_populates="stores")
    physical_devices = relationship("PhysicalDevice", back_populates="store")


# ---------------------------------------------------------------------------
# Channel Model
# ---------------------------------------------------------------------------

class Channel(Base):
    __tablename__ = "channels"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    device_types = relationship("DeviceType", back_populates="channel")


class DeviceType(Base):
    __tablename__ = "device_types"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    channel_id = Column(String(36), ForeignKey("channels.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    player_runtime = Column(String(64), nullable=False, default="chromium")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    channel = relationship("Channel", back_populates="device_types")
    capability_profiles = relationship("CapabilityProfile", back_populates="device_type")
    physical_devices = relationship("PhysicalDevice", back_populates="device_type")


class CapabilityProfile(Base):
    __tablename__ = "capability_profiles"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    device_type_id = Column(String(36), ForeignKey("device_types.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    resolution_w = Column(Integer, nullable=False, default=1920)
    resolution_h = Column(Integer, nullable=False, default=1080)
    orientation = Column(String(16), nullable=False, default="landscape")
    supported_formats = Column(ARRAY(String), nullable=False, default=[])
    max_file_size_bytes = Column(Integer, nullable=False, default=10_485_760)
    max_duration_sec = Column(Integer, nullable=False, default=30)
    supports_video = Column(Boolean, nullable=False, default=False)
    supports_animation = Column(Boolean, nullable=False, default=False)
    supports_interactive = Column(Boolean, nullable=False, default=False)
    pop_mode = Column(String(32), nullable=False, default="real_playback")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    device_type = relationship("DeviceType", back_populates="capability_profiles")


# ---------------------------------------------------------------------------
# Physical Devices
# ---------------------------------------------------------------------------

class PhysicalDevice(Base):
    __tablename__ = "physical_devices"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    device_type_id = Column(String(36), ForeignKey("device_types.id"), nullable=False, index=True)
    code = Column(String(128), nullable=False, unique=True, index=True)
    serial_number = Column(String(255), nullable=False, default="")
    hardware_fingerprint = Column(String(255), nullable=False, default="")
    os_version = Column(String(64), nullable=False, default="")
    ip_address = Column(String(45), nullable=False, default="")
    status = Column(
        String(32), nullable=False, default="unregistered",
        comment="Current state CACHE. See device_status_history for authoritative transitions.",
    )
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    current_manifest_id = Column(String(36), nullable=True)
    cache_size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    store = relationship("Store", back_populates="physical_devices")
    device_type = relationship("DeviceType", back_populates="physical_devices")
    certificates = relationship("DeviceCertificate", back_populates="device")
    status_history = relationship("DeviceStatusHistory", back_populates="device",
                                   order_by="DeviceStatusHistory.changed_at")
    logical_carriers = relationship("LogicalCarrier", back_populates="physical_device")


class DeviceCertificate(Base):
    __tablename__ = "device_certificates"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    physical_device_id = Column(String(36), ForeignKey("physical_devices.id"),
                                nullable=False, index=True)
    certificate_type = Column(String(32), nullable=False, default="ed25519")
    public_key = Column(Text, nullable=False, default="")
    fingerprint = Column(String(128), nullable=False, default="")
    issued_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    device = relationship("PhysicalDevice", back_populates="certificates")


class DeviceStatusHistory(Base):
    __tablename__ = "device_status_history"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    physical_device_id = Column(String(36), ForeignKey("physical_devices.id"),
                                nullable=False, index=True)
    old_status = Column(String(32), nullable=False, default="")
    new_status = Column(String(32), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    reason = Column(String(255), nullable=False, default="")
    source = Column(String(32), nullable=False, default="manual")
    details_json = Column(JSONB, nullable=True)

    device = relationship("PhysicalDevice", back_populates="status_history")


# ---------------------------------------------------------------------------
# Logical Carriers and Display Surfaces
# ---------------------------------------------------------------------------

class LogicalCarrier(Base):
    __tablename__ = "logical_carriers"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    physical_device_id = Column(String(36), ForeignKey("physical_devices.id"),
                                nullable=False, index=True)
    code = Column(String(128), nullable=False, unique=True, index=True)
    carrier_type = Column(String(32), nullable=False, default="direct")
    vendor_name = Column(String(255), nullable=False, default="")
    vendor_config_json = Column(JSONB, nullable=True)
    labels_count = Column(Integer, nullable=True)
    led_panels_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    physical_device = relationship("PhysicalDevice", back_populates="logical_carriers")
    display_surfaces = relationship("DisplaySurface", back_populates="logical_carrier")


class DisplaySurface(Base):
    __tablename__ = "display_surfaces"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    logical_carrier_id = Column(String(36), ForeignKey("logical_carriers.id"),
                                nullable=False, index=True)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    code = Column(String(128), nullable=False, unique=True, index=True)
    zone_id = Column(String(36), nullable=True)
    shelf_id = Column(String(36), nullable=True)
    category_id = Column(String(36), nullable=True)
    sku_group_id = Column(String(36), nullable=True)
    resolution_w = Column(Integer, nullable=False, default=1920)
    resolution_h = Column(Integer, nullable=False, default=1080)
    is_active = Column(Boolean, nullable=False, default=True)
    current_manifest_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    logical_carrier = relationship("LogicalCarrier", back_populates="display_surfaces")


# ---------------------------------------------------------------------------
# Required Table Count
# ---------------------------------------------------------------------------

REQUIRED_TABLES = frozenset({
    "branches", "clusters", "stores",
    "channels", "device_types", "capability_profiles",
    "physical_devices", "device_certificates", "device_status_history",
    "logical_carriers", "display_surfaces",
})
