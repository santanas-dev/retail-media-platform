"""Add inventory and booking: inventory_units, inventory_capacity_rules, campaign_bookings, booking_items.

Revision ID: 007
Revises: 006
Create Date: 2026-06-17

Creates:
  - inventory_units
  - inventory_capacity_rules
  - campaign_bookings
  - booking_items
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── inventory_units ────────────────────────────────────────────
    op.create_table(
        "inventory_units",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("code", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "store_id",
            UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "logical_carrier_id",
            UUID(as_uuid=True),
            sa.ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "display_surface_id",
            UUID(as_uuid=True),
            sa.ForeignKey("display_surfaces.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "capability_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("is_sellable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("comment", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── inventory_capacity_rules ───────────────────────────────────
    op.create_table(
        "inventory_capacity_rules",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "inventory_unit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inventory_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=False),
        sa.Column(
            "days_of_week_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[1,2,3,4,5,6,7]'"),
        ),
        sa.Column("time_from", sa.Time, nullable=False, server_default=sa.text("'00:00:00'")),
        sa.Column("time_to", sa.Time, nullable=False, server_default=sa.text("'23:59:59'")),
        sa.Column("loop_duration_seconds", sa.Integer, nullable=False),
        sa.Column("spot_duration_seconds", sa.Integer, nullable=False),
        sa.Column("max_spots_per_loop", sa.Integer, nullable=False),
        sa.Column(
            "max_share_of_voice",
            sa.Numeric(5, 4),
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── campaign_bookings ──────────────────────────────────────────
    op.create_table(
        "campaign_bookings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("date_from", sa.Date, nullable=False),
        sa.Column("date_to", sa.Date, nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── booking_items ──────────────────────────────────────────────
    op.create_table(
        "booking_items",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "inventory_unit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inventory_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("booked_spots_per_loop", sa.Integer, nullable=False),
        sa.Column("booked_share_of_voice", sa.Numeric(5, 4), nullable=True),
        sa.Column("date_from", sa.Date, nullable=False),
        sa.Column("date_to", sa.Date, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── CHECK constraints ──────────────────────────────────────────
    op.create_check_constraint(
        "ck_inv_unit_code",
        "inventory_units",
        "code ~ '^[a-z0-9_-]+$'",
    )
    op.create_check_constraint(
        "ck_inv_unit_status",
        "inventory_units",
        "status IN ('active', 'inactive', 'maintenance')",
    )
    op.create_check_constraint(
        "ck_cap_rule_dates",
        "inventory_capacity_rules",
        "valid_from <= valid_to",
    )
    op.create_check_constraint(
        "ck_cap_rule_times",
        "inventory_capacity_rules",
        "time_from < time_to",
    )
    op.create_check_constraint(
        "ck_cap_rule_loop",
        "inventory_capacity_rules",
        "loop_duration_seconds > 0",
    )
    op.create_check_constraint(
        "ck_cap_rule_spot",
        "inventory_capacity_rules",
        "spot_duration_seconds > 0",
    )
    op.create_check_constraint(
        "ck_cap_rule_spots",
        "inventory_capacity_rules",
        "max_spots_per_loop > 0",
    )
    op.create_check_constraint(
        "ck_cap_rule_sov",
        "inventory_capacity_rules",
        "max_share_of_voice >= 0 AND max_share_of_voice <= 1",
    )
    op.create_check_constraint(
        "ck_cap_rule_status",
        "inventory_capacity_rules",
        "status IN ('active', 'inactive')",
    )
    op.create_check_constraint(
        "ck_booking_dates",
        "campaign_bookings",
        "date_from <= date_to",
    )
    op.create_check_constraint(
        "ck_booking_status",
        "campaign_bookings",
        "status IN ('draft', 'reserved', 'confirmed', 'cancelled', 'expired')",
    )
    op.create_check_constraint(
        "ck_item_dates",
        "booking_items",
        "date_from <= date_to",
    )
    op.create_check_constraint(
        "ck_item_spots",
        "booking_items",
        "booked_spots_per_loop > 0",
    )

    # ── UNIQUE constraints ─────────────────────────────────────────
    op.create_unique_constraint(
        "uq_bi_booking_unit",
        "booking_items",
        ["booking_id", "inventory_unit_id"],
    )

    # ── INDEXes ────────────────────────────────────────────────────
    op.create_index("ix_inventory_units_channel", "inventory_units", ["channel_id"])
    op.create_index("ix_inventory_units_store", "inventory_units", ["store_id"])
    op.create_index("ix_cap_rules_unit", "inventory_capacity_rules", ["inventory_unit_id"])
    op.create_index("ix_bookings_campaign", "campaign_bookings", ["campaign_id"])
    op.create_index("ix_booking_items_booking", "booking_items", ["booking_id"])
    op.create_index("ix_booking_items_unit", "booking_items", ["inventory_unit_id"])


def downgrade() -> None:
    op.drop_table("booking_items")
    op.drop_table("campaign_bookings")
    op.drop_table("inventory_capacity_rules")
    op.drop_table("inventory_units")
