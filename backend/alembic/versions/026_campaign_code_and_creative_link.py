"""Add campaign_code + campaign_creatives link table (Step 37.4).

Revision ID: 026
Revises: 025
Create Date: 2026-06-22

- ALTER TABLE campaigns ADD COLUMN campaign_code VARCHAR(64) UNIQUE (nullable, for backward compat)
- CREATE TABLE campaign_creatives: links existing Campaign to Creative via creative_code
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add campaign_code to campaigns table (nullable for backward compat)
    op.add_column(
        "campaigns",
        sa.Column("campaign_code", sa.String(64), nullable=True),
    )
    op.create_unique_constraint("uq_campaigns_code", "campaigns", ["campaign_code"])
    op.create_index("ix_campaigns_code", "campaigns", ["campaign_code"])

    # Create campaign_creatives link table
    op.create_table(
        "campaign_creatives",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "creative_code",
            sa.String(64),
            sa.ForeignKey("creatives.creative_code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "slot_order",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_campaign_creatives_campaign", "campaign_creatives", ["campaign_id"])
    op.create_unique_constraint(
        "uq_campaign_creative", "campaign_creatives", ["campaign_id", "creative_code"]
    )


def downgrade() -> None:
    op.drop_table("campaign_creatives")
    op.drop_index("ix_campaigns_code", table_name="campaigns")
    op.drop_constraint("uq_campaigns_code", "campaigns", type_="unique")
    op.drop_column("campaigns", "campaign_code")
