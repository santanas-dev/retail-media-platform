"""Fix schema gaps for Organization & Channels API.

Revision ID: 003
Revises: 002
Create Date: 2026-06-16

Adds missing columns:
  - branches: is_active
  - clusters: is_active
  - channels: updated_at
  - device_types: created_at, updated_at
  - capability_profiles: updated_at
  - logical_carriers: updated_at
  - display_surfaces: updated_at
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # branches: add is_active
    op.add_column(
        "branches",
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
    )

    # clusters: add is_active
    op.add_column(
        "clusters",
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
    )

    # channels: add updated_at
    op.add_column(
        "channels",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # device_types: add created_at, updated_at
    op.add_column(
        "device_types",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "device_types",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # capability_profiles: add updated_at
    op.add_column(
        "capability_profiles",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # logical_carriers: add updated_at
    op.add_column(
        "logical_carriers",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # display_surfaces: add updated_at
    op.add_column(
        "display_surfaces",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("display_surfaces", "updated_at")
    op.drop_column("logical_carriers", "updated_at")
    op.drop_column("capability_profiles", "updated_at")
    op.drop_column("device_types", "updated_at")
    op.drop_column("device_types", "created_at")
    op.drop_column("channels", "updated_at")
    op.drop_column("clusters", "is_active")
    op.drop_column("branches", "is_active")
