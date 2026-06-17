"""020_device_content_sync_state

Revision ID: 020
Revises: 019
Create Date: 2026-06-17

Add Device Content Sync State Core — 4 tables for manifest apply events,
current manifest state, media cache reports, and per-item cache state.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_manifest_apply_events ─────────────────────────────
    op.create_table(
        "device_manifest_apply_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
        ),
        sa.Column("device_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reported_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("message", sa.String(512), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── device_current_manifest_states ───────────────────────────
    op.create_table(
        "device_current_manifest_states",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False, unique=True,
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("manifest_hash", sa.String(64), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── device_media_cache_reports ───────────────────────────────
    op.create_table(
        "device_media_cache_reports",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("cached_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("invalid_hash_count", sa.Integer(), nullable=False),
        sa.Column(
            "reported_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("device_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── device_media_cache_items ─────────────────────────────────
    op.create_table(
        "device_media_cache_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "manifest_item_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rendition_id", UUID(as_uuid=True),
            sa.ForeignKey("renditions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("reported_sha256", sa.String(64), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False,
        ),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("message", sa.String(512), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "gateway_device_id", "manifest_item_id",
            name="uq_device_media_cache_item",
        ),
    )


def downgrade() -> None:
    op.drop_table("device_media_cache_items")
    op.drop_table("device_media_cache_reports")
    op.drop_table("device_current_manifest_states")
    op.drop_table("device_manifest_apply_events")
