"""Add campaigns core: campaigns, campaign_channels, campaign_targets, campaign_renditions.

Revision ID: 006
Revises: 005
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── campaigns ──────────────────────────────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("order_id", UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("advertiser_id", UUID(as_uuid=True),
                  sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("brands.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("objective", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="draft"),
        sa.Column("planned_start_date", sa.Date, nullable=False),
        sa.Column("planned_end_date", sa.Date, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("budget", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False,
                  server_default="RUB"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "planned_start_date <= planned_end_date",
            name="ck_campaigns_dates"),
        sa.CheckConstraint("priority >= 0", name="ck_campaigns_priority"),
    )

    # ── campaign_channels ──────────────────────────────────────────
    op.create_table(
        "campaign_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("channel_id", UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("campaign_id", "channel_id",
                            name="uq_cc_campaign_channel"),
    )

    # ── campaign_targets ───────────────────────────────────────────
    op.create_table(
        "campaign_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("cluster_id", UUID(as_uuid=True),
                  sa.ForeignKey("clusters.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("store_id", UUID(as_uuid=True),
                  sa.ForeignKey("stores.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("logical_carrier_id", UUID(as_uuid=True),
                  sa.ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("display_surface_id", UUID(as_uuid=True),
                  sa.ForeignKey("display_surfaces.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── campaign_renditions ────────────────────────────────────────
    op.create_table(
        "campaign_renditions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("rendition_id", UUID(as_uuid=True),
                  sa.ForeignKey("renditions.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("weight", sa.Integer, nullable=False,
                  server_default="1"),
        sa.Column("position", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("campaign_id", "rendition_id",
                            name="uq_cr_campaign_rendition"),
    )


def downgrade() -> None:
    op.drop_table("campaign_renditions")
    op.drop_table("campaign_targets")
    op.drop_table("campaign_channels")
    op.drop_table("campaigns")
