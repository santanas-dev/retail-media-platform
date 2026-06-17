"""Manifest & Publication Core: SQLAlchemy ORM models."""

from sqlalchemy import (
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


class PublicationBatch(Base):
    """A single publication run bound to one approved schedule_run."""

    __tablename__ = "publication_batches"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    schedule_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(
        String(20), nullable=False, server_default="draft",
    )
    comment = Column(Text)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    approved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True))
    published_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    published_at = Column(DateTime(timezone=True))
    cancelled_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_at = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    targets = relationship(
        "PublicationTarget", back_populates="batch", lazy="selectin",
        cascade="all, delete-orphan",
    )
    manifest_versions = relationship(
        "ManifestVersion", back_populates="batch", lazy="selectin",
    )
    events = relationship(
        "PublicationEvent", back_populates="batch", lazy="selectin",
        order_by="PublicationEvent.created_at",
    )


class PublicationTarget(Base):
    """Concrete publication target — inventory_unit in a store on a channel."""

    __tablename__ = "publication_targets"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    publication_batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_unit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_units.id", ondelete="RESTRICT"),
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
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    batch = relationship("PublicationBatch", back_populates="targets")
    manifest_versions = relationship(
        "ManifestVersion", back_populates="target", lazy="selectin",
    )


class ManifestVersion(Base):
    """Versioned manifest document for a single publication target."""

    __tablename__ = "manifest_versions"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    publication_batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    publication_target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_targets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_version = Column(Integer, nullable=False)
    manifest_json = Column(JSONB, nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    signature = Column(String(512), nullable=True)
    status = Column(
        String(20), nullable=False, server_default="draft",
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )
    approved_at = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))

    batch = relationship("PublicationBatch", back_populates="manifest_versions")
    target = relationship("PublicationTarget", back_populates="manifest_versions")
    items = relationship(
        "ManifestItem", back_populates="manifest_version", lazy="selectin",
        cascade="all, delete-orphan",
    )


class ManifestItem(Base):
    """Link between a manifest version and a concrete schedule_item + media."""

    __tablename__ = "manifest_items"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    manifest_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schedule_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_items.id", ondelete="RESTRICT"),
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
    creative_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    media_path = Column(String(1000), nullable=False)
    sha256 = Column(String(64), nullable=False)
    date = Column(Date, nullable=False)
    time_from = Column(Time, nullable=False)
    time_to = Column(Time, nullable=False)
    loop_position = Column(Integer, nullable=False)
    spot_position = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    manifest_version = relationship("ManifestVersion", back_populates="items")


class PublicationEvent(Base):
    """Audit log entry for publication lifecycle events."""

    __tablename__ = "publication_events"

    id = Column(
        UUID(as_uuid=True), primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    publication_batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publication_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type = Column(String(30), nullable=False)
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    message = Column(Text)
    details_json = Column(
        JSONB, nullable=False, server_default=func.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(),
    )

    batch = relationship("PublicationBatch", back_populates="events")
