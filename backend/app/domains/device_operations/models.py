"""Device Operations: SQLAlchemy ORM models — Alert Rules, Alerts, Alert Events."""

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

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
    evaluation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_alert_evaluation_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    alert = relationship("DeviceAlert", back_populates="events", lazy="raise")


class DeviceAlertEvaluationRun(Base):
    """History record of one evaluation execution."""

    __tablename__ = "device_alert_evaluation_runs"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    triggered_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trigger_type = Column(
        String(16), nullable=False, default="manual", server_default="manual",
    )
    status = Column(String(24), nullable=False)
    started_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)
    evaluated_rules_count = Column(Integer(), nullable=False, default=0, server_default="0")
    created_count = Column(Integer(), nullable=False, default=0, server_default="0")
    repeated_count = Column(Integer(), nullable=False, default=0, server_default="0")
    reopened_count = Column(Integer(), nullable=False, default=0, server_default="0")
    skipped_count = Column(Integer(), nullable=False, default=0, server_default="0")
    failed_rules_count = Column(Integer(), nullable=False, default=0, server_default="0")
    duration_ms = Column(Integer(), nullable=True)
    details_json = Column(
        JSONB(), nullable=False, server_default="{}",
    )
    error_message = Column(Text(), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    rule_results = relationship(
        "DeviceAlertEvaluationRuleResult", back_populates="run", lazy="raise",
    )


class DeviceAlertEvaluationRuleResult(Base):
    """Per-rule result within an evaluation run."""

    __tablename__ = "device_alert_evaluation_rule_results"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_alert_evaluation_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_alert_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_code = Column(String(64), nullable=False)
    alert_type = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)
    checked_devices_count = Column(Integer(), nullable=False, default=0, server_default="0")
    matched_devices_count = Column(Integer(), nullable=False, default=0, server_default="0")
    created_count = Column(Integer(), nullable=False, default=0, server_default="0")
    repeated_count = Column(Integer(), nullable=False, default=0, server_default="0")
    reopened_count = Column(Integer(), nullable=False, default=0, server_default="0")
    skipped_count = Column(Integer(), nullable=False, default=0, server_default="0")
    error_message = Column(Text(), nullable=True)
    details_json = Column(
        JSONB(), nullable=False, server_default="{}",
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    run = relationship(
        "DeviceAlertEvaluationRun", back_populates="rule_results", lazy="raise",
    )

# ═══════════════════════════════════════════════════════════════════════
#  Runtime Configuration (Step 18)
# ═══════════════════════════════════════════════════════════════════════


class DeviceRuntimeConfigProfile(Base):
    __tablename__ = "device_runtime_config_profiles"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    config_json = Column(JSONB, nullable=False)
    config_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(DateTime(timezone=True))
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    assignments = relationship(
        "DeviceRuntimeConfigAssignment", back_populates="profile",
    )


class DeviceRuntimeConfigAssignment(Base):
    __tablename__ = "device_runtime_config_assignments"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("device_runtime_config_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope_type = Column(String(10), nullable=False)
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    store_id = Column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=True,
    )
    channel_id = Column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=True,
    )
    priority = Column(Integer, nullable=False, server_default="0")
    enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(DateTime(timezone=True))
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    profile = relationship(
        "DeviceRuntimeConfigProfile", back_populates="assignments",
    )


class DeviceRuntimeConfigRequest(Base):
    __tablename__ = "device_runtime_config_requests"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    config_profile_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    effective_config_hash = Column(String(64), nullable=False)
    response_status = Column(String(13), nullable=False)
    requested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    details_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


# ═══════════════════════════════════════════════════════════════════════
#  Content Sync State (Step 20)
# ═══════════════════════════════════════════════════════════════════════


class DeviceManifestApplyEvent(Base):
    """Audit log: device reports manifest apply attempt."""

    __tablename__ = "device_manifest_apply_events"

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
        nullable=False,
    )
    manifest_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    device_reported_at = Column(DateTime(timezone=True))
    reported_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    error_code = Column(String(64))
    message = Column(String(512))
    details_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class DeviceCurrentManifestState(Base):
    """Current manifest state per device (upsert)."""

    __tablename__ = "device_current_manifest_states"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gateway_device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manifest_hash = Column(String(64))
    status = Column(
        String(20), nullable=False, server_default="unknown",
    )
    last_applied_at = Column(DateTime(timezone=True))
    last_failed_at = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
    details_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class DeviceMediaCacheReport(Base):
    """Audit log: device submits a batch media cache report."""

    __tablename__ = "device_media_cache_reports"

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
        nullable=False,
    )
    manifest_hash = Column(String(64), nullable=False)
    total_items = Column(Integer, nullable=False)
    cached_count = Column(Integer, nullable=False)
    missing_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)
    invalid_hash_count = Column(Integer, nullable=False)
    reported_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    device_reported_at = Column(DateTime(timezone=True))
    details_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class DeviceMediaCacheItem(Base):
    """Per-item media cache state on a device (upsert)."""

    __tablename__ = "device_media_cache_items"

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
        nullable=False,
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("renditions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expected_sha256 = Column(String(64), nullable=False)
    reported_sha256 = Column(String(64))
    status = Column(String(20), nullable=False)
    file_size_bytes = Column(Integer)
    cached_at = Column(DateTime(timezone=True))
    last_seen_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
    error_code = Column(String(64))
    message = Column(String(512))
    details_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        UniqueConstraint(
            "gateway_device_id", "manifest_item_id",
            name="uq_device_media_cache_item",
        ),
    )
