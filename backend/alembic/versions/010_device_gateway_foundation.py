"""Add Device Gateway Foundation.

Revision ID: 010
Revises: 009
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── gateway_devices ──────────────────────────────────────────
    op.create_table(
        "gateway_devices",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("device_code", sa.String(64), unique=True, nullable=False),
        sa.Column("device_name", sa.String(255)),
        sa.Column(
            "physical_device_id", UUID(as_uuid=True),
            sa.ForeignKey("physical_devices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "logical_carrier_id", UUID(as_uuid=True),
            sa.ForeignKey("logical_carriers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "display_surface_id", UUID(as_uuid=True),
            sa.ForeignKey("display_surfaces.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "channel_id", UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "store_id", UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.Text),
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

    op.create_check_constraint(
        "ck_gd_status",
        "gateway_devices",
        sa.text("status IN ('pending','active','disabled','lost','retired')"),
    )

    op.create_index("ix_gd_status", "gateway_devices", ["status"])
    op.create_index("ix_gd_store", "gateway_devices", ["store_id"])
    op.create_index("ix_gd_channel", "gateway_devices", ["channel_id"])

    # ── device_credentials ─────────────────────────────────────────
    op.create_table(
        "device_credentials",
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
            "credential_type",
            sa.String(20),
            nullable=False,
            server_default="shared_secret",
        ),
        sa.Column("public_key", sa.Text, nullable=True),
        sa.Column("secret_hash", sa.String(255), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_check_constraint(
        "ck_dc_type",
        "device_credentials",
        sa.text("credential_type IN ('shared_secret','certificate')"),
    )
    op.create_check_constraint(
        "ck_dc_status",
        "device_credentials",
        sa.text("status IN ('active','revoked','expired')"),
    )

    op.create_index("ix_dc_device", "device_credentials", ["gateway_device_id"])
    op.create_index("ix_dc_status", "device_credentials", ["status"])

    # ── device_sessions ────────────────────────────────────────────
    op.create_table(
        "device_sessions",
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
            "credential_id", UUID(as_uuid=True),
            sa.ForeignKey("device_credentials.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("access_token_hash", sa.String(64), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("client_ip", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_ds_device", "device_sessions", ["gateway_device_id"])
    op.create_index("ix_ds_token_hash", "device_sessions", ["access_token_hash"])
    op.create_index("ix_ds_credential", "device_sessions", ["credential_id"])

    # ── device_heartbeats ──────────────────────────────────────────
    op.create_table(
        "device_heartbeats",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50)),
        sa.Column("device_time", sa.DateTime(timezone=True)),
        sa.Column("app_version", sa.String(50)),
        sa.Column("os_version", sa.String(100)),
        sa.Column("storage_free_mb", sa.Integer),
        sa.Column("cache_items_count", sa.Integer),
        sa.Column("current_manifest_hash", sa.String(64)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column(
            "details_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_check_constraint(
        "ck_dh_status",
        "device_heartbeats",
        sa.text("status IN ('ok','warning','error')"),
    )

    op.create_index("ix_dh_device", "device_heartbeats", ["gateway_device_id"])
    op.create_index("ix_dh_created", "device_heartbeats", ["created_at"])

    # ── device_events ──────────────────────────────────────────────
    op.create_table(
        "device_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default="info",
        ),
        sa.Column("message", sa.Text),
        sa.Column(
            "details_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_check_constraint(
        "ck_de_type",
        "device_events",
        sa.text(
            "event_type IN ("
            "'device_registered','credential_issued','credential_rotated',"
            "'credential_revoked','device_login_success','device_login_failed',"
            "'heartbeat_received','device_disabled','device_reactivated',"
            "'invalid_token','validation_failed'"
            ")",
        ),
    )
    op.create_check_constraint(
        "ck_de_severity",
        "device_events",
        sa.text("severity IN ('info','warning','error')"),
    )

    op.create_index("ix_de_device", "device_events", ["gateway_device_id"])
    op.create_index("ix_de_type", "device_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("device_events")
    op.drop_table("device_heartbeats")
    op.drop_table("device_sessions")
    op.drop_table("device_credentials")
    op.drop_table("gateway_devices")
