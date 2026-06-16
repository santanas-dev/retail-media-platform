"""Initial multichannel schema: organization + channels & devices.

Revision ID: 001
Revises: None
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # UUID generation support
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── Organization ──────────────────────────────────────────────

    op.create_table(
        "branches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "timezone",
            sa.String(50),
            server_default="Europe/Moscow",
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
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
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
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_clusters_branch_id", "clusters", ["branch_id"])

    op.create_table(
        "stores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("address", sa.Text),
        sa.Column(
            "timezone",
            sa.String(50),
            server_default="Europe/Moscow",
        ),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_stores_cluster_id", "stores", ["cluster_id"])

    # ── Channels & Devices ────────────────────────────────────────

    op.create_table(
        "channels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "device_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("channel_id", "code"),
    )
    op.create_index("ix_device_types_channel_id", "device_types", ["channel_id"])

    op.create_table(
        "capability_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "device_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("resolution", sa.String(20)),
        sa.Column("orientation", sa.String(20), server_default="landscape"),
        sa.Column("formats_json", postgresql.JSONB),
        sa.Column("max_file_size", sa.BigInteger),
        sa.Column("max_duration", sa.Integer),
        sa.Column("interactive", sa.Boolean, server_default=sa.text("false")),
        sa.Column("proof_type", sa.String(50), nullable=False),
        sa.Column("cache_policy", sa.String(50), server_default="full"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_capability_profiles_device_type_id",
        "capability_profiles",
        ["device_type_id"],
    )

    op.create_table(
        "physical_devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("serial_number", sa.String(255)),
        sa.Column("hw_fingerprint", sa.String(512)),
        sa.Column("status", sa.String(50), server_default="offline"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_physical_devices_store_id", "physical_devices", ["store_id"]
    )
    op.create_index(
        "ix_physical_devices_device_type_id",
        "physical_devices",
        ["device_type_id"],
    )

    op.create_table(
        "logical_carriers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "physical_device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physical_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("zone", sa.String(100)),
        sa.Column("position", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_logical_carriers_physical_device_id",
        "logical_carriers",
        ["physical_device_id"],
    )

    op.create_table(
        "display_surfaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "logical_carrier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "capability_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("resolution", sa.String(20)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_display_surfaces_logical_carrier_id",
        "display_surfaces",
        ["logical_carrier_id"],
    )
    op.create_index(
        "ix_display_surfaces_capability_profile_id",
        "display_surfaces",
        ["capability_profile_id"],
    )


def downgrade() -> None:
    op.drop_table("display_surfaces")
    op.drop_table("logical_carriers")
    op.drop_table("physical_devices")
    op.drop_table("capability_profiles")
    op.drop_table("device_types")
    op.drop_table("channels")
    op.drop_table("stores")
    op.drop_table("clusters")
    op.drop_table("branches")
