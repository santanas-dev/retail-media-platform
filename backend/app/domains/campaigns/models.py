"""Campaigns Core domain: ORM models."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Campaign(Base):
    """Campaign — advertising campaign linked to an order."""

    __tablename__ = "campaigns"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advertiser_id = Column(
        UUID(as_uuid=True),
        ForeignKey("advertisers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name = Column(String(255), nullable=False)
    objective = Column(String(100))
    status = Column(
        String(20), nullable=False, server_default="draft"
    )
    planned_start_date = Column(Date, nullable=False)
    planned_end_date = Column(Date, nullable=False)
    priority = Column(Integer, nullable=False, server_default="0")
    budget = Column(Numeric(15, 2))
    currency = Column(String(3), nullable=False, server_default="RUB")
    comment = Column(Text)
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
    rejection_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "planned_start_date <= planned_end_date",
            name="ck_campaigns_dates",
        ),
        CheckConstraint("priority >= 0", name="ck_campaigns_priority"),
    )

    channels = relationship(
        "CampaignChannel", back_populates="campaign", lazy="selectin",
        cascade="all, delete-orphan",
    )
    targets = relationship(
        "CampaignTarget", back_populates="campaign", lazy="selectin",
        cascade="all, delete-orphan",
    )
    renditions = relationship(
        "CampaignRendition", back_populates="campaign", lazy="selectin",
        cascade="all, delete-orphan",
    )


class CampaignChannel(Base):
    """CampaignChannel — link between campaign and a media channel."""

    __tablename__ = "campaign_channels"

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
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("campaign_id", "channel_id", name="uq_cc_campaign_channel"),
    )

    campaign = relationship("Campaign", back_populates="channels")


class CampaignTarget(Base):
    """CampaignTarget — infrastructure targeting for a campaign."""

    __tablename__ = "campaign_targets"

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
    target_type = Column(String(20), nullable=False)
    branch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=True,
    )
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("Campaign", back_populates="targets")


class CampaignRendition(Base):
    """CampaignRendition — validated rendition assigned to a campaign."""

    __tablename__ = "campaign_renditions"

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
    rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("renditions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weight = Column(Integer, nullable=False, server_default="1")
    position = Column(Integer)
    is_active = Column(Boolean, nullable=False, server_default=func.text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("campaign_id", "rendition_id", name="uq_cr_campaign_rendition"),
    )

    campaign = relationship("Campaign", back_populates="renditions")
