"""Device Gateway Foundation: SQLAlchemy ORM models."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class GatewayDevice(Base):
    """Device identity within the gateway."""

    __tablename__ = "gateway_devices"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    device_code = Column(String(64), unique=True, nullable=False)
    device_name = Column(String(255))
    physical_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("physical_devices.id", ondelete="RESTRICT"),
        nullable=True,
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
    status = Column(
        String(20), nullable=False, server_default="pending",
    )
    last_seen_at = Column(DateTime(timezone=True))
    registered_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    disabled_at = Column(DateTime(timezone=True))
    comment = Column(Text)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    credentials = relationship(
        "DeviceCredential", back_populates="device", lazy="selectin",
    )
    sessions = relationship(
        "DeviceSession", back_populates="device", lazy="selectin",
    )
    heartbeats = relationship(
        "DeviceHeartbeat", back_populates="device", lazy="selectin",
    )
    events = relationship(
        "DeviceEvent", back_populates="device", lazy="selectin",
        order_by="DeviceEvent.created_at",
    )
    manifest_requests = relationship(
        "DeviceManifestRequest", back_populates="device", lazy="selectin",
        order_by="DeviceManifestRequest.created_at",
    )
    media_requests = relationship(
        "DeviceMediaRequest", back_populates="device", lazy="selectin",
        order_by="DeviceMediaRequest.created_at",
    )
    pop_events = relationship(
        "ProofOfPlayEvent", back_populates="device", lazy="selectin",
        order_by="ProofOfPlayEvent.created_at",
    )


class DeviceCredential(Base):
    """Device authentication credential (shared secret or certificate)."""

    __tablename__ = "device_credentials"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credential_type = Column(
        String(20), nullable=False, server_default="shared_secret",
    )
    public_key = Column(Text, nullable=True)
    secret_hash = Column(String(255), nullable=True)
    fingerprint = Column(String(64), nullable=True)
    status = Column(
        String(20), nullable=False, server_default="active",
    )
    issued_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    expires_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="credentials")
    sessions = relationship(
        "DeviceSession", back_populates="credential", lazy="selectin",
    )


class DeviceSession(Base):
    """Short-lived device access token session."""

    __tablename__ = "device_sessions"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credential_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_credentials.id", ondelete="RESTRICT"),
        nullable=False,
    )
    access_token_hash = Column(String(64), nullable=False)
    issued_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    client_ip = Column(String(45))
    user_agent = Column(String(500))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="sessions")
    credential = relationship("DeviceCredential", back_populates="sessions")


class DeviceHeartbeat(Base):
    """Heartbeat record from a device."""

    __tablename__ = "device_heartbeats"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(50))
    device_time = Column(DateTime(timezone=True))
    app_version = Column(String(50))
    os_version = Column(String(100))
    storage_free_mb = Column(Integer)
    cache_items_count = Column(Integer)
    current_manifest_hash = Column(String(64))
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="heartbeats")


class DeviceEvent(Base):
    """Audit log for gateway events."""

    __tablename__ = "device_events"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type = Column(String(30), nullable=False)
    severity = Column(
        String(10), nullable=False, server_default="info",
    )
    message = Column(Text)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="events")


class DeviceManifestRequest(Base):
    """Audit log of device manifest requests."""

    __tablename__ = "device_manifest_requests"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    publication_target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_targets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    request_status = Column(String(20), nullable=False)
    response_hash = Column(String(64), nullable=True)
    client_manifest_hash = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    message = Column(Text, nullable=True)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="manifest_requests")


class DeviceMediaRequest(Base):
    """Audit log for media download attempts by gateway devices."""

    __tablename__ = "device_media_requests"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    publication_target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_targets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    request_status = Column(String(30), nullable=False)
    media_path = Column(String(1000), nullable=True)
    expected_sha256 = Column(String(64), nullable=True)
    client_cached_sha256 = Column(String(64), nullable=True)
    response_size_bytes = Column(BigInteger, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    message = Column(Text, nullable=True)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="media_requests")


class ProofOfPlayEvent(Base):
    """Proof-of-play event submitted by a gateway device."""

    __tablename__ = "proof_of_play_events"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_event_id = Column(
        UUID(as_uuid=True), nullable=False,
    )
    manifest_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    publication_target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_targets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    schedule_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=True,
    )
    campaign_rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaign_renditions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("renditions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    creative_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    played_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    duration_ms = Column(Integer, nullable=True)
    play_status = Column(String(20), nullable=True)
    validation_status = Column(String(20), nullable=False, default="accepted")
    media_sha256 = Column(String(64), nullable=True)
    expected_sha256 = Column(String(64), nullable=True)
    player_version = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    rejection_reason = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    device = relationship("GatewayDevice", back_populates="pop_events")
