"""Add hierarchy fields: cluster.code, store.format, store.status;
create kso_devices table (Step 37.1).

Revision ID: 024
Revises: 023
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Cluster: add code + unique constraint ──────────────────────────
    op.add_column(
        "clusters",
        sa.Column("code", sa.String(50), nullable=True),
    )
    op.create_unique_constraint(
        "uq_cluster_branch_code", "clusters", ["branch_id", "code"],
    )

    # ── Store: add format + status ─────────────────────────────────────
    op.add_column(
        "stores",
        sa.Column("format", sa.String(50), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )

    # ── KSO Devices table ──────────────────────────────────────────────
    op.create_table(
        "kso_devices",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "store_id",
            UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_code",
            sa.String(64),
            unique=True,
            nullable=False,
        ),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="inactive",
        ),
        sa.Column(
            "channel",
            sa.String(20),
            nullable=False,
            server_default="kso",
        ),
        sa.Column("runtime_version", sa.String(32), nullable=True),
        sa.Column("player_version", sa.String(32), nullable=True),
        sa.Column("sidecar_version", sa.String(32), nullable=True),
        sa.Column("state_adapter_version", sa.String(32), nullable=True),
        sa.Column("manifest_version", sa.String(64), nullable=True),
        sa.Column(
            "screen_width",
            sa.Integer(),
            nullable=False,
            server_default="1920",
        ),
        sa.Column(
            "screen_height",
            sa.Integer(),
            nullable=False,
            server_default="1080",
        ),
        sa.Column(
            "ad_zone_width",
            sa.Integer(),
            nullable=False,
            server_default="1440",
        ),
        sa.Column(
            "ad_zone_height",
            sa.Integer(),
            nullable=False,
            server_default="1080",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
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
    op.create_index("ix_kso_devices_store_id", "kso_devices", ["store_id"])


def downgrade() -> None:
    # ── KSO Devices table ──────────────────────────────────────────────
    op.drop_index("ix_kso_devices_store_id", table_name="kso_devices")
    op.drop_table("kso_devices")

    # ── Store: drop format + status ────────────────────────────────────
    op.drop_column("stores", "status")
    op.drop_column("stores", "format")

    # ── Cluster: drop constraint + code ────────────────────────────────
    op.drop_constraint("uq_cluster_branch_code", "clusters", type_="unique")
    op.drop_column("clusters", "code")
