"""016_device_alerts_core

Revision ID: 016
Revises: 015
Create Date: 2026-06-17

Add device_alert_rules, device_alerts, device_alert_events tables
and seed default alert rules (idempotent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALERT_TYPES = [
    "device_offline", "no_manifest", "no_media", "no_pop",
    "manifest_validation_failed", "media_validation_failed",
    "media_storage_error", "pop_rejected_high", "duplicate_events_high",
    "batch_rejected",
]

SEVERITIES = ["info", "warning", "critical"]
ALERT_STATUSES = ["open", "acknowledged", "resolved"]
EVENT_TYPES = ["created", "repeated", "acknowledged", "resolved", "reopened"]

# Default rules — idempotent seed (ON CONFLICT DO NOTHING on code)
DEFAULT_RULES = [
    ("device_offline", "Device Offline", "Устройство неактивно более 30 минут",
     "device_offline", "critical", True, None, 30, None),
    ("media_storage_error", "Media Storage Error", "Ошибка доступа к хранилищу медиа",
     "media_storage_error", "critical", True, None, 60, None),
    ("manifest_validation_failed", "Manifest Validation Failed",
     "Ошибка валидации манифеста", "manifest_validation_failed", "warning", True, None, 60, None),
    ("media_validation_failed", "Media Validation Failed",
     "Ошибка валидации медиафайла", "media_validation_failed", "warning", True, None, 60, None),
    ("pop_rejected_high", "PoP Rejected High",
     "Высокая доля отклонённых Proof-of-Play событий",
     "pop_rejected_high", "warning", True,
     '{"error_rate": 0.20, "min_total": 10}', 120, None),
    ("duplicate_events_high", "Duplicate Events High",
     "Высокая доля дублирующихся событий", "duplicate_events_high", "warning", True,
     '{"duplicate_rate": 0.20, "min_total": 10}', 120, None),
    ("batch_rejected", "Batch Rejected", "Отклонённый PoP batch",
     "batch_rejected", "warning", True, None, 120, None),
    # Disabled by default — no false positives without evidence of expected activity
    ("no_manifest", "No Manifest", "Отсутствие запросов манифеста",
     "no_manifest", "warning", False, None, 120, None),
    ("no_media", "No Media", "Отсутствие загрузок медиа",
     "no_media", "warning", False, None, 120, None),
    ("no_pop", "No PoP", "Отсутствие Proof-of-Play событий",
     "no_pop", "warning", False, None, 120, None),
]


def upgrade() -> None:
    # ── device_alert_rules ────────────────────────────────────────
    op.create_table(
        "device_alert_rules",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "alert_type", sa.String(64), nullable=False,
        ),
        sa.Column(
            "severity", sa.String(16), nullable=False,
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "threshold_json", JSONB(), nullable=True,
        ),
        sa.Column(
            "window_minutes", sa.Integer(), nullable=False, server_default="60",
        ),
        sa.Column(
            "scope_json", JSONB(), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── device_alerts ─────────────────────────────────────────────
    op.create_table(
        "device_alerts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "rule_id", UUID(as_uuid=True),
            sa.ForeignKey("device_alert_rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="open",
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "store_id", UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "channel_id", UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "resolved_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("dedup_key", sa.String(512), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Partial unique index: only one active (open/acknowledged) alert per dedup_key
    op.create_index(
        "uq_active_alert_dedup",
        "device_alerts",
        ["dedup_key"],
        unique=True,
        postgresql_where=("status IN ('open', 'acknowledged')"),
    )

    # ── device_alert_events ───────────────────────────────────────
    op.create_table(
        "device_alert_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "alert_id", UUID(as_uuid=True),
            sa.ForeignKey("device_alerts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("old_status", sa.String(16), nullable=True),
        sa.Column("new_status", sa.String(16), nullable=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_device_alert_events_alert_id_created",
        "device_alert_events",
        ["alert_id", "created_at"],
    )

    # ── Seed default rules (idempotent) ──────────────────────────
    seed_default_rules()


def downgrade() -> None:
    op.drop_table("device_alert_events")
    op.drop_index("uq_active_alert_dedup", table_name="device_alerts")
    op.drop_table("device_alerts")
    op.drop_table("device_alert_rules")


def seed_default_rules() -> None:
    """Idempotent seed of default alert rules."""
    import json as _json
    from datetime import timezone as _tz
    from datetime import datetime as _dt

    now = _dt.now(_tz.utc)

    conn = op.get_bind()
    for code, name, desc, atype, sev, en, thresh, win, scope in DEFAULT_RULES:
        threshold_val = _json.loads(thresh) if thresh else None
        scope_val = _json.loads(scope) if scope else None

        conn.execute(
            sa.text("""
                INSERT INTO device_alert_rules
                    (code, name, description, alert_type, severity, enabled,
                     threshold_json, window_minutes, scope_json,
                     created_at, updated_at)
                VALUES
                    (:code, :name, :desc, :atype, :sev, :enabled,
                     :threshold, :win, :scope, :now, :now)
                ON CONFLICT (code) DO NOTHING
            """),
            {
                "code": code, "name": name, "desc": desc,
                "atype": atype, "sev": sev, "enabled": en,
                "threshold": _json.dumps(threshold_val) if threshold_val else None,
                "win": win, "scope": _json.dumps(scope_val) if scope_val else None,
                "now": now,
            },
        )
