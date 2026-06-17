"""017_alert_evaluation_runs

Revision ID: 017
Revises: 016
Create Date: 2026-06-17

Add device_alert_evaluation_runs and device_alert_evaluation_rule_results tables,
plus evaluation_run_id FK on device_alert_events.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_alert_evaluation_runs ─────────────────────────────
    op.create_table(
        "device_alert_evaluation_runs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "triggered_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "trigger_type", sa.String(16), nullable=False,
            server_default="manual",
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "evaluated_rules_count", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "repeated_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "reopened_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "skipped_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "failed_rules_count", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "details_json", JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── device_alert_evaluation_rule_results ─────────────────────
    op.create_table(
        "device_alert_evaluation_rule_results",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "run_id", UUID(as_uuid=True),
            sa.ForeignKey("device_alert_evaluation_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_id", UUID(as_uuid=True),
            sa.ForeignKey("device_alert_rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "checked_devices_count", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "matched_devices_count", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "repeated_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "reopened_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "skipped_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        "ix_rule_results_run_id_created",
        "device_alert_evaluation_rule_results",
        ["run_id", "created_at"],
    )

    # ── ALTER device_alert_events: add evaluation_run_id ─────────
    op.add_column(
        "device_alert_events",
        sa.Column(
            "evaluation_run_id", UUID(as_uuid=True),
            sa.ForeignKey(
                "device_alert_evaluation_runs.id", ondelete="RESTRICT",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("device_alert_events", "evaluation_run_id")
    op.drop_index(
        "ix_rule_results_run_id_created",
        table_name="device_alert_evaluation_rule_results",
    )
    op.drop_table("device_alert_evaluation_rule_results")
    op.drop_table("device_alert_evaluation_runs")
