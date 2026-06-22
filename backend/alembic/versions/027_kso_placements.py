"""Add kso_placements table for test KSO schedule/placement (Step 37.5).

Revision ID: 027
Revises: 026
Create Date: 2026-06-22

- CREATE TABLE kso_placements: links campaign_code, creative_code, device_code
  with time window (starts_at, ends_at). Minimal placement for test KSO chain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kso_placements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "placement_code",
            sa.String(64),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "campaign_code",
            sa.String(64),
            sa.ForeignKey("campaigns.campaign_code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "creative_code",
            sa.String(64),
            sa.ForeignKey("creatives.creative_code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_code",
            sa.String(64),
            sa.ForeignKey("kso_devices.device_code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ends_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "slot_order",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
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
    op.create_index("ix_kso_placements_code", "kso_placements", ["placement_code"])
    op.create_index("ix_kso_placements_campaign", "kso_placements", ["campaign_code"])
    op.create_index("ix_kso_placements_creative", "kso_placements", ["creative_code"])
    op.create_index("ix_kso_placements_device", "kso_placements", ["device_code"])
    op.create_index("ix_kso_placements_status", "kso_placements", ["status"])
    op.create_index("ix_kso_placements_starts", "kso_placements", ["starts_at"])


def downgrade() -> None:
    op.drop_table("kso_placements")
