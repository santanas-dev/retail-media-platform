"""Test KSO Manifest Generation domain."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def _pk():
    return uuid4()


def _now():
    return datetime.now(timezone.utc)


class GeneratedManifest(Base):
    """Minimal generated manifest for test KSO technical validation.

    Stores safe KSO-sidecar-compatible manifest_body_json.
    FK to safe codes (not raw UUIDs) for placement/campaign/device.
    """

    __tablename__ = "generated_manifests"

    id = Column(PGUUID, primary_key=True, default=_pk)
    manifest_code = Column(String(64), unique=True, nullable=False, index=True)

    # FK on safe codes
    device_code = Column(
        String(64),
        ForeignKey("kso_devices.device_code", ondelete="RESTRICT"),
        nullable=False,
    )
    placement_code = Column(
        String(64),
        ForeignKey("kso_placements.placement_code", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_code = Column(
        String(64),
        ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
        nullable=False,
    )

    status = Column(String(30), nullable=False, default="generated", index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    manifest_body_json = Column(JSON, nullable=False)
    item_count = Column(Integer, nullable=False, default=0)
    media_ref_format = Column(String(50), nullable=True)

    # Audit
    generated_by = Column(PGUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by = Column(PGUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    # Relationships
    generated_by_user = relationship("User", foreign_keys=[generated_by])
    published_by_user = relationship("User", foreign_keys=[published_by])
