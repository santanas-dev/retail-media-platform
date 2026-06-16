"""
Organization domain: ORM models for branches, clusters, stores.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Branch(Base):
    """Geographic or organizational branch (филиал)."""

    __tablename__ = "branches"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    timezone = Column(String(50), server_default="Europe/Moscow")
    is_active = Column(Boolean, server_default=func.text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    clusters = relationship("Cluster", back_populates="branch", lazy="selectin")


class Cluster(Base):
    """Group of stores within a branch (кластер)."""

    __tablename__ = "clusters"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name = Column(String(255), nullable=False)
    branch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, server_default=func.text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    branch = relationship("Branch", back_populates="clusters")
    stores = relationship("Store", back_populates="cluster", lazy="selectin")


class Store(Base):
    """Individual retail store (магазин)."""

    __tablename__ = "stores"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    address = Column(Text)
    timezone = Column(String(50), server_default="Europe/Moscow")
    is_active = Column(Boolean, server_default=func.text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    cluster = relationship("Cluster", back_populates="stores")
