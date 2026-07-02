"""${message}

Revision ID: 001
Revises:
Create Date: 2026-07-02

Phase 2: Foundation tables — organization, channels, devices, surfaces.
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
    # -----------------------------------------------------------------------
    # Organization
    # -----------------------------------------------------------------------
    op.create_table(
        "branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "stores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cluster_id", sa.String(36), sa.ForeignKey("clusters.id"), nullable=False, index=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # -----------------------------------------------------------------------
    # Channel Model
    # -----------------------------------------------------------------------
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "device_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False, index=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("player_runtime", sa.String(64), nullable=False, server_default="chromium"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "capability_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_type_id", sa.String(36), sa.ForeignKey("device_types.id"),
                  nullable=False, index=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("resolution_w", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("resolution_h", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("orientation", sa.String(16), nullable=False, server_default="landscape"),
        sa.Column("supported_formats", postgresql.ARRAY(sa.String()), nullable=False,
                  server_default="{}"),
        sa.Column("max_file_size_bytes", sa.Integer(), nullable=False, server_default="10485760"),
        sa.Column("max_duration_sec", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("supports_video", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("supports_animation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("supports_interactive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pop_mode", sa.String(32), nullable=False, server_default="real_playback"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # -----------------------------------------------------------------------
    # Physical Devices
    # -----------------------------------------------------------------------
    op.create_table(
        "physical_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("device_type_id", sa.String(36), sa.ForeignKey("device_types.id"),
                  nullable=False, index=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("serial_number", sa.String(255), nullable=False, server_default=""),
        sa.Column("hardware_fingerprint", sa.String(255), nullable=False, server_default=""),
        sa.Column("os_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="unregistered",
                  comment="Current state CACHE. See device_status_history for authoritative "
                          "transitions."),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_manifest_id", sa.String(36), nullable=True),
        sa.Column("cache_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "device_certificates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("physical_device_id", sa.String(36), sa.ForeignKey("physical_devices.id"),
                  nullable=False, index=True),
        sa.Column("certificate_type", sa.String(32), nullable=False, server_default="ed25519"),
        sa.Column("public_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("fingerprint", sa.String(128), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "device_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("physical_device_id", sa.String(36), sa.ForeignKey("physical_devices.id"),
                  nullable=False, index=True),
        sa.Column("old_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("details_json", postgresql.JSONB(), nullable=True),
    )

    # -----------------------------------------------------------------------
    # Logical Carriers and Display Surfaces
    # -----------------------------------------------------------------------
    op.create_table(
        "logical_carriers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("physical_device_id", sa.String(36), sa.ForeignKey("physical_devices.id"),
                  nullable=False, index=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("carrier_type", sa.String(32), nullable=False, server_default="direct"),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("vendor_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("labels_count", sa.Integer(), nullable=True),
        sa.Column("led_panels_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "display_surfaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("logical_carrier_id", sa.String(36), sa.ForeignKey("logical_carriers.id"),
                  nullable=False, index=True),
        sa.Column("store_id", sa.String(36), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("zone_id", sa.String(36), nullable=True),
        sa.Column("shelf_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("sku_group_id", sa.String(36), nullable=True),
        sa.Column("resolution_w", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("resolution_h", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_manifest_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("display_surfaces")
    op.drop_table("logical_carriers")
    op.drop_table("device_status_history")
    op.drop_table("device_certificates")
    op.drop_table("physical_devices")
    op.drop_table("capability_profiles")
    op.drop_table("device_types")
    op.drop_table("channels")
    op.drop_table("stores")
    op.drop_table("clusters")
    op.drop_table("branches")
