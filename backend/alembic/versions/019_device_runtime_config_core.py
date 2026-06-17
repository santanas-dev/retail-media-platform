"""019_device_runtime_config_core

Revision ID: 019
Revises: 018
Create Date: 2026-06-17

Add device runtime configuration profiles, assignments, and request audit.
Includes idempotent seed: default_runtime_config profile + global assignment.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_runtime_config_profiles ───────────────────────────
    op.create_table(
        "device_runtime_config_profiles",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("code", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", JSONB(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column(
            "updated_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_rt_profiles_version_min",
        "device_runtime_config_profiles",
        sa.text("version >= 1"),
    )
    op.create_check_constraint(
        "ck_rt_profiles_hash_len",
        "device_runtime_config_profiles",
        sa.text("length(config_hash) = 64"),
    )

    # ── device_runtime_config_assignments ────────────────────────
    op.create_table(
        "device_runtime_config_assignments",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "profile_id", UUID(as_uuid=True),
            sa.ForeignKey(
                "device_runtime_config_profiles.id", ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(10), nullable=False),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "store_id", UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column(
            "channel_id", UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column(
            "updated_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
    )

    # CHECK constraints: assignments
    op.create_check_constraint(
        "ck_rt_assign_scope_type",
        "device_runtime_config_assignments",
        sa.text("scope_type IN ('global', 'channel', 'store', 'device')"),
    )
    op.create_check_constraint(
        "ck_rt_assign_priority_min",
        "device_runtime_config_assignments",
        sa.text("priority >= 0"),
    )
    # Scope combination checks
    op.create_check_constraint(
        "ck_rt_assign_global",
        "device_runtime_config_assignments",
        sa.text(
            "(scope_type != 'global') OR "
            "(gateway_device_id IS NULL AND store_id IS NULL AND channel_id IS NULL)"
        ),
    )
    op.create_check_constraint(
        "ck_rt_assign_channel",
        "device_runtime_config_assignments",
        sa.text(
            "(scope_type != 'channel') OR "
            "(channel_id IS NOT NULL AND gateway_device_id IS NULL AND store_id IS NULL)"
        ),
    )
    op.create_check_constraint(
        "ck_rt_assign_store",
        "device_runtime_config_assignments",
        sa.text(
            "(scope_type != 'store') OR "
            "(store_id IS NOT NULL AND gateway_device_id IS NULL AND channel_id IS NULL)"
        ),
    )
    op.create_check_constraint(
        "ck_rt_assign_device",
        "device_runtime_config_assignments",
        sa.text(
            "(scope_type != 'device') OR "
            "(gateway_device_id IS NOT NULL AND store_id IS NULL AND channel_id IS NULL)"
        ),
    )

    # ── device_runtime_config_requests ───────────────────────────
    op.create_table(
        "device_runtime_config_requests",
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
            "config_profile_ids", sa.ARRAY(UUID(as_uuid=True)), nullable=False,
        ),
        sa.Column("effective_config_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.String(13), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_check_constraint(
        "ck_rt_requests_status",
        "device_runtime_config_requests",
        sa.text("response_status IN ('ok', 'not_modified', 'error')"),
    )
    op.create_check_constraint(
        "ck_rt_requests_hash_len",
        "device_runtime_config_requests",
        sa.text("length(effective_config_hash) = 64"),
    )

    # ── Seed: default runtime config ────────────────────────────
    import hashlib, json

    default_config = {
        "heartbeat_interval_sec": 60,
        "manifest_refresh_interval_sec": 60,
        "media_download_timeout_sec": 30,
        "media_cache_max_mb": 1024,
        "pop_batch_max_events": 500,
        "pop_flush_interval_sec": 300,
        "offline_mode_enabled": True,
        "allowed_mime_types": [
            "image/jpeg", "image/png", "video/mp4", "video/webm",
        ],
        "max_media_file_mb": 500,
        "clock_skew_tolerance_sec": 300,
        "log_level": "info",
    }
    config_str = json.dumps(default_config, sort_keys=True, separators=(",", ":"))
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()

    # Use connection.execute with bind params as dict
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO device_runtime_config_profiles "
            "(code, name, description, config_json, config_hash, version, enabled) "
            "VALUES (:code, :name, :desc, CAST(:json AS jsonb), :hash, 1, true) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": "default_runtime_config",
            "name": "Default Runtime Configuration",
            "desc": "Default runtime configuration for all devices",
            "json": config_str,
            "hash": config_hash,
        },
    )

    # Idempotent global assignment
    op.execute(
        sa.text("""
            INSERT INTO device_runtime_config_assignments
                (profile_id, scope_type, priority, enabled)
            SELECT id, 'global', 0, true
            FROM device_runtime_config_profiles
            WHERE code = 'default_runtime_config'
              AND NOT EXISTS (
                  SELECT 1 FROM device_runtime_config_assignments a
                  JOIN device_runtime_config_profiles p ON a.profile_id = p.id
                  WHERE p.code = 'default_runtime_config'
                    AND a.scope_type = 'global'
              )
        """)
    )


def downgrade() -> None:
    op.drop_table("device_runtime_config_requests")
    op.drop_table("device_runtime_config_assignments")
    op.drop_table("device_runtime_config_profiles")
