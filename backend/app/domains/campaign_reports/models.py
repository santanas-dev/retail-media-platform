"""Campaign Delivery Reporting Core: ORM models."""

import sqlalchemy as sa
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class CampaignDeliverySnapshot(Base):
    """Saved snapshot of campaign delivery metrics at a point in time."""

    __tablename__ = "campaign_delivery_snapshots"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    generated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    period_from = Column(DateTime(timezone=True), nullable=False)
    period_to = Column(DateTime(timezone=True), nullable=False)

    snapshot_status = Column(
        String(20), nullable=False, server_default="generated",
    )
    delivery_status = Column(
        String(30), nullable=False, server_default="not_started",
    )
    delivery_risk_status = Column(
        String(10), nullable=False, server_default="ok",
    )

    # Planning / Publication
    planned_stores = Column(Integer, nullable=False, server_default="0")
    planned_devices = Column(Integer, nullable=False, server_default="0")
    published_targets = Column(Integer, nullable=False, server_default="0")
    published_devices = Column(Integer, nullable=False, server_default="0")

    # Manifest / Sync
    manifest_available_devices = Column(Integer, nullable=False, server_default="0")
    manifest_applied_devices = Column(Integer, nullable=False, server_default="0")
    manifest_failed_devices = Column(Integer, nullable=False, server_default="0")

    # Media Cache
    cache_ready_devices = Column(Integer, nullable=False, server_default="0")
    cache_missing_devices = Column(Integer, nullable=False, server_default="0")
    cache_failed_devices = Column(Integer, nullable=False, server_default="0")
    cache_invalid_hash_devices = Column(Integer, nullable=False, server_default="0")

    # PoP
    actual_play_count = Column(Integer, nullable=False, server_default="0")
    unique_devices_with_pop = Column(Integer, nullable=False, server_default="0")
    unique_stores_with_pop = Column(Integer, nullable=False, server_default="0")

    # Delivery Health
    devices_ok = Column(Integer, nullable=False, server_default="0")
    devices_warning = Column(Integer, nullable=False, server_default="0")
    devices_critical = Column(Integer, nullable=False, server_default="0")

    # Rollup
    stores_total = Column(Integer, nullable=False, server_default="0")
    stores_with_delivery = Column(Integer, nullable=False, server_default="0")
    stores_with_errors = Column(Integer, nullable=False, server_default="0")
    channels_total = Column(Integer, nullable=False, server_default="0")

    details_json = Column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"),
    )

    generated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        CheckConstraint("period_from <= period_to", name="ck_cds_period"),
    )
