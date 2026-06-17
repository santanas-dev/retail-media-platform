"""Add Device Media Delivery Core.

Revision ID: 012
Revises: 011
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_media_requests ──────────────────────────────────────
    op.create_table(
        "device_media_requests",
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
            nullable=True,
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "publication_target_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_targets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "request_status", sa.String(30), nullable=False,
        ),
        sa.Column("media_path", sa.String(1000), nullable=True),
        sa.Column("expected_sha256", sa.String(64), nullable=True),
        sa.Column("client_cached_sha256", sa.String(64), nullable=True),
        sa.Column("response_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column(
            "details_json", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── CHECK request_status ───────────────────────────────────────
    op.create_check_constraint(
        "ck_media_requests_status",
        "device_media_requests",
        sa.text(
            "request_status IN ("
            "'served','not_modified','not_found','forbidden',"
            "'validation_failed','storage_error'"
            ")"
        ),
    )

    # ── CHECK sha256 is 64 hex chars when set ──────────────────────
    # expected_sha256: NULL or 64 hex chars
    op.create_check_constraint(
        "ck_media_requests_expected_sha256",
        "device_media_requests",
        sa.text(
            "expected_sha256 IS NULL "
            "OR expected_sha256 ~ '^[a-f0-9]{64}$'"
        ),
    )
    # client_cached_sha256: NULL or 64 hex chars
    op.create_check_constraint(
        "ck_media_requests_client_sha256",
        "device_media_requests",
        sa.text(
            "client_cached_sha256 IS NULL "
            "OR client_cached_sha256 ~ '^[a-f0-9]{64}$'"
        ),
    )
    # response_size_bytes: NULL or >= 0
    op.create_check_constraint(
        "ck_media_requests_response_size",
        "device_media_requests",
        sa.text(
            "response_size_bytes IS NULL "
            "OR response_size_bytes >= 0"
        ),
    )

    # ── Indexes ────────────────────────────────────────────────────
    op.create_index(
        "ix_media_requests_device_id",
        "device_media_requests", ["gateway_device_id"],
    )
    op.create_index(
        "ix_media_requests_mi_id",
        "device_media_requests", ["manifest_item_id"],
    )
    op.create_index(
        "ix_media_requests_mv_id",
        "device_media_requests", ["manifest_version_id"],
    )
    op.create_index(
        "ix_media_requests_target_id",
        "device_media_requests", ["publication_target_id"],
    )
    op.create_index(
        "ix_media_requests_status",
        "device_media_requests", ["request_status"],
    )
    op.create_index(
        "ix_media_requests_created_at",
        "device_media_requests", ["created_at"],
    )
    op.create_index(
        "ix_media_requests_device_created",
        "device_media_requests",
        ["gateway_device_id", "created_at"],
    )

    # ── Expand device_events.event_type CHECK ──────────────────────
    op.execute("""
        ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type
    """)
    op.create_check_constraint(
        "ck_de_type",
        "device_events",
        sa.text(
            "event_type IN ("
            "'device_registered','credential_issued','credential_rotated',"
            "'credential_revoked','device_login_success','device_login_failed',"
            "'heartbeat_received','device_disabled','device_reactivated',"
            "'invalid_token','validation_failed',"
            "'manifest_served','manifest_not_modified','manifest_not_found',"
            "'manifest_forbidden',"
            "'media_served','media_not_modified','media_not_found',"
            "'media_forbidden','media_validation_failed','media_storage_error'"
            ")"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_media_requests_device_created", table_name="device_media_requests")
    op.drop_index("ix_media_requests_created_at", table_name="device_media_requests")
    op.drop_index("ix_media_requests_status", table_name="device_media_requests")
    op.drop_index("ix_media_requests_target_id", table_name="device_media_requests")
    op.drop_index("ix_media_requests_mv_id", table_name="device_media_requests")
    op.drop_index("ix_media_requests_mi_id", table_name="device_media_requests")
    op.drop_index("ix_media_requests_device_id", table_name="device_media_requests")
    op.drop_table("device_media_requests")

    # Restore old CHECK constraint
    op.execute("""
        ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type
    """)
    op.create_check_constraint(
        "ck_de_type",
        "device_events",
        sa.text(
            "event_type IN ("
            "'device_registered','credential_issued','credential_rotated',"
            "'credential_revoked','device_login_success','device_login_failed',"
            "'heartbeat_received','device_disabled','device_reactivated',"
            "'invalid_token','validation_failed',"
            "'manifest_served','manifest_not_modified','manifest_not_found',"
            "'manifest_forbidden'"
            ")"
        ),
    )
