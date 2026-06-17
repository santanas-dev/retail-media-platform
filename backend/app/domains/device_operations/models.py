"""Device Operations: SQLAlchemy ORM models — Alert Rules, Alerts, Alert Events."""

from sqlalchemy import (
    Boolean,
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


class DeviceAlertRule(Base):
    """Definition of an alert evaluation rule."""

    __tablename__ = "device_alert_rules"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text(), nullable=True)
    alert_type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    enabled = Column(Boolean(), nullable=False, default=True, server_default="true")
    threshold_json = Column(JSONB(), nullable=True)
    window_minutes = Column(Integer(), nullable=False, default=60)
    scope_json = Column(JSONB(), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    alerts = relationship("DeviceAlert", back_populates="rule", lazy="raise")


class DeviceAlert(Base):
    """A triggered alert instance."""

    __tablename__ = "device_alerts"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_alert_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    alert_type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="open", server_default="open")
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=True,
    )
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=True,
    )
    first_seen_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    last_seen_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dedup_key = Column(String(512), nullable=False)
    title = Column(String(512), nullable=False)
    message = Column(Text(), nullable=True)
    details_json = Column(
        JSONB(), nullable=False, server_default="{}",
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    rule = relationship("DeviceAlertRule", back_populates="alerts", lazy="raise")
    events = relationship("DeviceAlertEvent", back_populates="alert", lazy="raise")


class DeviceAlertEvent(Base):
    """Audit trail of alert status changes."""

    __tablename__ = "device_alert_events"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    alert_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_alerts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(16), nullable=False)
    old_status = Column(String(16), nullable=True)
    new_status = Column(String(16), nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    message = Column(Text(), nullable=True)
    details_json = Column(
        JSONB(), nullable=False, server_default="{}",
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    alert = relationship("DeviceAlert", back_populates="events", lazy="raise")
