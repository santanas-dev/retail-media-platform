"""Add creative_code to creatives; make advertiser_id nullable for one-KSO pilot (Step 37.3).

Revision ID: 025
Revises: 024
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add creative_code column (nullable → fill existing → set not null)
    op.add_column("creatives", sa.Column("creative_code", sa.String(64), nullable=True))
    # Generate codes for existing creatives
    op.execute("UPDATE creatives SET creative_code = 'legacy_' || substring(id::text, 1, 8) WHERE creative_code IS NULL")
    op.alter_column("creatives", "creative_code", nullable=False)
    op.create_unique_constraint("uq_creative_code", "creatives", ["creative_code"])

    # Make advertiser_id nullable for pilot
    op.alter_column("creatives", "advertiser_id", nullable=True)


def downgrade() -> None:
    # Set advertiser_id NOT NULL — remove rows with NULL first
    op.execute("DELETE FROM creatives WHERE advertiser_id IS NULL")
    op.alter_column("creatives", "advertiser_id", nullable=False)

    op.drop_constraint("uq_creative_code", "creatives", type_="unique")
    op.drop_column("creatives", "creative_code")
