"""Add advertisers, brands, contracts, orders.

Revision ID: 004
Revises: 003
Create Date: 2026-06-16

Creates the commercial base tables:
  - advertisers
  - brands
  - contracts
  - orders
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── advertisers ──
    op.create_table(
        "advertisers",
        sa.Column(
            "id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(500), nullable=True),
        sa.Column("inn", sa.String(12), nullable=True, unique=True),
        sa.Column("kpp", sa.String(9), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="active | inactive | blocked",
        ),
        sa.Column("contacts_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_check_constraint(
        "ck_advertisers_status",
        "advertisers",
        "status IN ('active', 'inactive', 'blocked')",
    )

    # ── brands ──
    op.create_table(
        "brands",
        sa.Column(
            "id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "advertiser_id",
            sa.UUID,
            sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="active | inactive",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_unique_constraint(
        "uq_brands_advertiser_name", "brands", ["advertiser_id", "name"]
    )
    op.create_check_constraint(
        "ck_brands_status", "brands", "status IN ('active', 'inactive')"
    )

    # ── contracts ──
    op.create_table(
        "contracts",
        sa.Column(
            "id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "advertiser_id",
            sa.UUID,
            sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            comment="draft | active | expired | closed | cancelled",
        ),
        sa.Column("amount_limit", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="RUB",
        ),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_unique_constraint(
        "uq_contracts_advertiser_number", "contracts", ["advertiser_id", "number"]
    )
    op.create_index("ix_contracts_status", "contracts", ["status"])
    op.create_check_constraint(
        "ck_contracts_status",
        "contracts",
        "status IN ('draft', 'active', 'expired', 'closed', 'cancelled')",
    )

    # ── orders ──
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "advertiser_id",
            sa.UUID,
            sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "brand_id",
            sa.UUID,
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "contract_id",
            sa.UUID,
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            comment="draft | pending | approved | in_progress | completed | cancelled",
        ),
        sa.Column("planned_budget", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="RUB",
        ),
        sa.Column("planned_start_date", sa.Date, nullable=True),
        sa.Column("planned_end_date", sa.Date, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_unique_constraint(
        "uq_orders_advertiser_number", "orders", ["advertiser_id", "number"]
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        "status IN ('draft', 'pending', 'approved', 'in_progress', 'completed', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("contracts")
    op.drop_table("brands")
    op.drop_table("advertisers")
