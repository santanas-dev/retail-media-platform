"""Add schedules and schedule_slots tables (Step 39.1.3).

Revision ID: 033_schedules_and_slots
Revises: 032_add_scan_status
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = '033_schedules_and_slots'
down_revision: Union[str, None] = '032_add_scan_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("schedule_code", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft", index=True),
        sa.Column("campaign_code", sa.String(64),
                  sa.ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
                  nullable=True, index=True),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Europe/Moscow"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "schedule_slots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("slot_code", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("schedule_id", UUID(as_uuid=True),
                  sa.ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("placement_code", sa.String(64),
                  sa.ForeignKey("kso_placements.placement_code", ondelete="RESTRICT"),
                  nullable=True, index=True),
        sa.Column("creative_code", sa.String(64),
                  sa.ForeignKey("creatives.creative_code", ondelete="RESTRICT"),
                  nullable=True, index=True),
        sa.Column("channel_code", sa.String(64), nullable=True),
        sa.Column("start_time", sa.Time(timezone=False), nullable=False),
        sa.Column("end_time", sa.Time(timezone=False), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False, server_default="0"),
        sa.Column("slot_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("schedule_slots")
    op.drop_table("schedules")
