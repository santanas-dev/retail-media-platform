"""Media Library domain: ORM models."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
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


class Creative(Base):
    """Creative — business entity for an advertising asset."""

    __tablename__ = "creatives"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
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
        index=True,
    )
    name = Column(String(255), nullable=False)
    status = Column(
        String(20), nullable=False, server_default="draft"
    )
    comment = Column(Text)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    versions = relationship(
        "CreativeVersion", back_populates="creative", lazy="selectin"
    )


class CreativeVersion(Base):
    """CreativeVersion — a specific uploaded file version of a creative."""

    __tablename__ = "creative_versions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    creative_id = Column(
        UUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(
        String(20), nullable=False, server_default="uploaded"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("creative_id", "version", name="uq_cv_creative_version"),
    )

    creative = relationship("Creative", back_populates="versions")
    renditions = relationship(
        "Rendition", back_populates="creative_version", lazy="selectin"
    )


class Rendition(Base):
    """Rendition — prepared variant linked to a channel/capability profile."""

    __tablename__ = "renditions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    creative_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    capability_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    file_path = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(
        String(20), nullable=False, server_default="pending"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    creative_version = relationship("CreativeVersion", back_populates="renditions")
    validations = relationship(
        "RenditionValidation", back_populates="rendition", lazy="selectin"
    )


class RenditionValidation(Base):
    """RenditionValidation — result of a single validation check."""

    __tablename__ = "rendition_validations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    rendition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("renditions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    check_type = Column(String(50), nullable=False)
    result = Column(
        String(20), nullable=False, server_default="pending"
    )
    details_json = Column(JSONB, nullable=False, server_default=func.text("'{}'::jsonb"))
    checked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    rendition = relationship("Rendition", back_populates="validations")
