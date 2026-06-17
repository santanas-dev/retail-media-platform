"""Add Device Manifest Delivery Core.

Revision ID: 011
Revises: 010
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_manifest_requests ──────────────────────────────────
    op.create_table(
        "device_manifest_requests",
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
            nullable=True,
        ),
        sa.Column(
            "publication_target_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_targets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "request_status", sa.String(20), nullable=False,
        ),
        sa.Column("response_hash", sa.String(64), nullable=True),
        sa.Column("client_manifest_hash", sa.String(64), nullable=True),
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

    # ── CHECK constraint ──────────────────────────────────────────
    op.create_check_constraint(
        "ck_device_manifest_requests_status",
        "device_manifest_requests",
        sa.text(
            "request_status IN "
            "('served', 'not_modified', 'not_found', 'forbidden', 'validation_failed')"
        ),
    )

    # ── Indexes ───────────────────────────────────────────────────
    op.create_index(
        "ix_manifest_requests_device_id",
        "device_manifest_requests", ["gateway_device_id"],
    )
    op.create_index(
        "ix_manifest_requests_manifest_version",
        "device_manifest_requests", ["manifest_version_id"],
    )
    op.create_index(
        "ix_manifest_requests_target_id",
        "device_manifest_requests", ["publication_target_id"],
    )
    op.create_index(
        "ix_manifest_requests_status",
        "device_manifest_requests", ["request_status"],
    )
    op.create_index(
        "ix_manifest_requests_created_at",
        "device_manifest_requests", ["created_at"],
    )
    op.create_index(
        "ix_manifest_requests_device_created",
        "device_manifest_requests",
        ["gateway_device_id", "created_at"],
    )

    # ── Expand device_events.event_type CHECK ─────────────────────
    # Drop old constraint, add new one with extra values
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


def downgrade() -> None:
    op.drop_index("ix_manifest_requests_device_created", table_name="device_manifest_requests")
    op.drop_index("ix_manifest_requests_created_at", table_name="device_manifest_requests")
    op.drop_index("ix_manifest_requests_status", table_name="device_manifest_requests")
    op.drop_index("ix_manifest_requests_target_id", table_name="device_manifest_requests")
    op.drop_index("ix_manifest_requests_manifest_version", table_name="device_manifest_requests")
    op.drop_index("ix_manifest_requests_device_id", table_name="device_manifest_requests")
    op.drop_table("device_manifest_requests")

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
            "'invalid_token','validation_failed'"
            ")"
        ),
    )
