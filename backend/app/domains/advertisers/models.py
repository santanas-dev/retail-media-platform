"""Advertisers & Commercial Base domain: ORM models."""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Advertiser(Base):
    """Advertiser — legal entity or client."""

    __tablename__ = "advertisers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name = Column(String(255), nullable=False)
    legal_name = Column(String(500))
    inn = Column(String(12), unique=True)
    kpp = Column(String(9))
    status = Column(
        String(20), nullable=False, server_default="active"
    )
    contacts_json = Column(JSONB, nullable=False, server_default="{}")
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    brands = relationship("Brand", back_populates="advertiser", lazy="selectin")
    contracts = relationship("Contract", back_populates="advertiser", lazy="selectin")
    orders = relationship("Order", back_populates="advertiser", lazy="selectin")


class Brand(Base):
    """Brand — trademark within an advertiser."""

    __tablename__ = "brands"

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
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    status = Column(
        String(20), nullable=False, server_default="active"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("advertiser_id", "name", name="uq_brands_advertiser_name"),
    )

    advertiser = relationship("Advertiser", back_populates="brands")
    orders = relationship("Order", back_populates="brand", lazy="selectin")


class Contract(Base):
    """Contract — legal basis for placement."""

    __tablename__ = "contracts"

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
    number = Column(String(100), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=False)
    status = Column(
        String(20), nullable=False, server_default="draft"
    )
    amount_limit = Column(Numeric(15, 2))
    currency = Column(String(3), nullable=False, server_default="RUB")
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("advertiser_id", "number", name="uq_contracts_advertiser_number"),
    )

    advertiser = relationship("Advertiser", back_populates="contracts")
    orders = relationship("Order", back_populates="contract", lazy="selectin")


class Order(Base):
    """Order — commercial placement request / package."""

    __tablename__ = "orders"

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
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    number = Column(String(100), nullable=False)
    name = Column(String(500), nullable=False)
    status = Column(
        String(20), nullable=False, server_default="draft"
    )
    planned_budget = Column(Numeric(15, 2))
    currency = Column(String(3), nullable=False, server_default="RUB")
    planned_start_date = Column(Date)
    planned_end_date = Column(Date)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("advertiser_id", "number", name="uq_orders_advertiser_number"),
    )

    advertiser = relationship("Advertiser", back_populates="orders")
    brand = relationship("Brand", back_populates="orders")
    contract = relationship("Contract", back_populates="orders")
