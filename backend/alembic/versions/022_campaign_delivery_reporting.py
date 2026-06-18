"""Add campaign_delivery_snapshots table and campaign_reports permissions.

Revision ID: 022
Revises: 021
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = [
    ("campaign_reports.read", "Read campaign delivery reports",
     "campaign_reports", "read", "View campaign delivery reports"),
    ("campaign_reports.manage", "Manage campaign delivery reports",
     "campaign_reports", "manage", "Generate campaign delivery snapshots"),
]

# Role names → additional permissions
ROLE_PERMISSION_UPDATES = {
    "System Administrator": ["campaign_reports.read", "campaign_reports.manage"],
    "Security Administrator": ["campaign_reports.read"],
    "Operations": ["campaign_reports.read", "campaign_reports.manage"],
    "Analyst": ["campaign_reports.read", "campaign_reports.manage"],
    "Ad Manager": ["campaign_reports.read", "campaign_reports.manage"],
}


def upgrade() -> None:
    # ── Table ──────────────────────────────────────────────────────
    op.create_table(
        "campaign_delivery_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),

        # Snapshot generation status
        sa.Column("snapshot_status", sa.String(20), nullable=False,
                  server_default="generated"),
        # Campaign delivery status (computed)
        sa.Column("delivery_status", sa.String(30), nullable=False,
                  server_default="not_started"),
        # Delivery risk aggregate
        sa.Column("delivery_risk_status", sa.String(10), nullable=False,
                  server_default="ok"),

        # Planning / Publication
        sa.Column("planned_stores", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planned_devices", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_targets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_devices", sa.Integer(), nullable=False, server_default="0"),

        # Manifest / Sync
        sa.Column("manifest_available_devices", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("manifest_applied_devices", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("manifest_failed_devices", sa.Integer(), nullable=False,
                  server_default="0"),

        # Media Cache
        sa.Column("cache_ready_devices", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("cache_missing_devices", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("cache_failed_devices", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("cache_invalid_hash_devices", sa.Integer(), nullable=False,
                  server_default="0"),

        # PoP
        sa.Column("actual_play_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("unique_devices_with_pop", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("unique_stores_with_pop", sa.Integer(), nullable=False,
                  server_default="0"),

        # Delivery Health
        sa.Column("devices_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("devices_warning", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("devices_critical", sa.Integer(), nullable=False, server_default="0"),

        # Rollup
        sa.Column("stores_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stores_with_delivery", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("stores_with_errors", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("channels_total", sa.Integer(), nullable=False, server_default="0"),

        # Flexible payload (aggregates only, no secrets)
        sa.Column("details_json", JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),

        # Audit
        sa.Column("generated_by_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── Indexes ────────────────────────────────────────────────────
    op.create_index("idx_cds_campaign", "campaign_delivery_snapshots",
                    ["campaign_id"])
    op.create_index("idx_cds_generated", "campaign_delivery_snapshots",
                    ["generated_at"])
    op.create_index("idx_cds_campaign_generated", "campaign_delivery_snapshots",
                    ["campaign_id", "generated_at"])
    op.create_index("idx_cds_campaign_period", "campaign_delivery_snapshots",
                    ["campaign_id", "period_from", "period_to"])

    # ── New index for join performance ─────────────────────────────
    op.create_index("ix_dcms_manifest_version_id",
                    "device_current_manifest_states",
                    ["manifest_version_id"])

    # ── Seed permissions (idempotent) ──────────────────────────────
    conn = op.get_bind()

    for code, name, resource, action, desc in NEW_PERMISSIONS:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (code, name, resource, action, description)
                VALUES (:code, :name, :resource, :action, :desc)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,
                    description=EXCLUDED.description
            """),
            {"code": code, "name": name, "resource": resource,
             "action": action, "desc": desc},
        )

    for role_name, perm_codes in ROLE_PERMISSION_UPDATES.items():
        for pc in perm_codes:
            conn.execute(
                sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                    FROM roles r, permissions p
                    WHERE r.name = :role_name AND p.code = :perm_code
                    ON CONFLICT DO NOTHING
                """),
                {"role_name": role_name, "perm_code": pc},
            )


def downgrade() -> None:
    op.drop_index("idx_cds_campaign_period", table_name="campaign_delivery_snapshots")
    op.drop_index("idx_cds_campaign_generated", table_name="campaign_delivery_snapshots")
    op.drop_index("idx_cds_generated", table_name="campaign_delivery_snapshots")
    op.drop_index("idx_cds_campaign", table_name="campaign_delivery_snapshots")
    op.drop_index("ix_dcms_manifest_version_id",
                  table_name="device_current_manifest_states")
    op.drop_table("campaign_delivery_snapshots")
