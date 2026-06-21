"""Add auth RBAC RLS tables: user_rls_scopes, login_audit_events, admin_audit_events,
mfa_settings; add is_archived/archived_at/archived_by to users.

Revision ID: 023
Revises: 022
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Role → Permission updates for device_service ──────────────────────────

# device_service must have NO human portal permissions.
# It keeps only service/API permissions: devices.gateway.*
DEVICE_SERVICE_CURRENT_PERMISSIONS = [
    # device_service role in seed.py has empty list currently.
    # After migration, assign only:
    "devices.gateway.read",
    "devices.gateway.manage",
    "devices.gateway.credentials",
]


def upgrade() -> None:
    # ── users: archived fields ──────────────────────────────────────
    op.add_column("users",
                  sa.Column("is_archived", sa.Boolean(),
                            server_default=sa.text("false"), nullable=True))
    op.add_column("users",
                  sa.Column("archived_at", sa.DateTime(timezone=True),
                            nullable=True))
    op.add_column("users",
                  sa.Column("archived_by",
                            UUID(as_uuid=True),
                            sa.ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True))

    # ── user_rls_scopes ──────────────────────────────────────────────
    op.create_table(
        "user_rls_scopes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_value", sa.String(255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(),
                  server_default=sa.text("true")),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.UniqueConstraint("user_id", "scope_type", "scope_value",
                            name="uq_user_rls_scope"),
    )
    op.create_index("idx_user_rls_scopes_user", "user_rls_scopes", ["user_id"])

    # ── login_audit_events ───────────────────────────────────────────
    op.create_table(
        "login_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("result_code", sa.String(50), nullable=True),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("ip_hash", sa.String(128), nullable=True),
        sa.Column("user_agent_hash", sa.String(128), nullable=True),
    )
    op.create_index("idx_login_audit_user_time", "login_audit_events",
                    ["user_id", "occurred_at"])
    op.create_index("idx_login_audit_time", "login_audit_events",
                    ["occurred_at"])

    # ── admin_audit_events ───────────────────────────────────────────
    op.create_table(
        "admin_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_ref", sa.String(255), nullable=True),
        sa.Column("details_json", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_admin_audit_actor_time", "admin_audit_events",
                    ["actor_user_id", "occurred_at"])
    op.create_index("idx_admin_audit_time", "admin_audit_events",
                    ["occurred_at"])
    op.create_index("idx_admin_audit_action_time", "admin_audit_events",
                    ["action", "occurred_at"])

    # ── mfa_settings ─────────────────────────────────────────────────
    op.create_table(
        "mfa_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("mfa_required", sa.Boolean(),
                  server_default=sa.text("false")),
        sa.Column("mfa_enabled", sa.Boolean(),
                  server_default=sa.text("false")),
        sa.Column("method", sa.String(20), nullable=True),
        sa.Column("secret_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_mfa_settings_user"),
    )
    op.create_index("idx_mfa_settings_user", "mfa_settings", ["user_id"])

    # ── device_service permissions ───────────────────────────────────
    # Ensure device_service role exists and has only service permissions
    conn = op.get_bind()

    # Get device_service role
    role = conn.execute(
        sa.text("SELECT id FROM roles WHERE code = 'device_service'")
    ).fetchone()
    if role:
        role_id = role[0]
        # Remove all existing permissions for device_service
        conn.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": role_id},
        )
        # Insert service-only permissions
        for perm_code in DEVICE_SERVICE_CURRENT_PERMISSIONS:
            perm = conn.execute(
                sa.text("SELECT id FROM permissions WHERE code = :code"),
                {"code": perm_code},
            ).fetchone()
            if perm:
                conn.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id) "
                        "VALUES (:rid, :pid) "
                        "ON CONFLICT (role_id, permission_id) DO NOTHING"
                    ),
                    {"rid": role_id, "pid": perm[0]},
                )


def downgrade() -> None:
    # ── device_service permissions: restore empty ───────────────────
    conn = op.get_bind()
    role = conn.execute(
        sa.text("SELECT id FROM roles WHERE code = 'device_service'")
    ).fetchone()
    if role:
        conn.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": role[0]},
        )

    # ── Drop tables (reverse order) ─────────────────────────────────
    op.drop_table("mfa_settings")
    op.drop_table("admin_audit_events")
    op.drop_table("login_audit_events")
    op.drop_table("user_rls_scopes")

    # ── Drop columns from users ─────────────────────────────────────
    op.drop_constraint("users_archived_by_fkey", "users", type_="foreignkey")
    op.drop_column("users", "archived_by")
    op.drop_column("users", "archived_at")
    op.drop_column("users", "is_archived")
