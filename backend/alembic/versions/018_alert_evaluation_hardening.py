"""018_alert_evaluation_hardening

Revision ID: 018
Revises: 017
Create Date: 2026-06-17

Add DB-level CHECK constraints, limit error_message to VARCHAR(500),
and sanitize existing raw exception messages from failed runs.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Sanitize existing raw error_messages ───────────────────
    # Replace raw Python exception text with generic safe messages
    raw_patterns = [
        "_evaluate_",
        "takes ",
        "positional arguments",
        "Traceback",
        "File \"",
        "TypeError",
        "AttributeError",
    ]

    for table in [
        "device_alert_evaluation_runs",
        "device_alert_evaluation_rule_results",
    ]:
        for pattern in raw_patterns:
            op.execute(
                sa.text(
                    f"UPDATE {table} SET error_message = 'Unexpected evaluation error' "
                    f"WHERE error_message LIKE :pat"
                ).bindparams(pat=f"%{pattern}%")
            )

    # ── 2. Constrain error_message to VARCHAR(500) ────────────────
    op.alter_column(
        "device_alert_evaluation_runs",
        "error_message",
        type_=sa.String(500),
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "device_alert_evaluation_rule_results",
        "error_message",
        type_=sa.String(500),
        existing_type=sa.Text(),
        nullable=True,
    )

    # ── 3. CHECK constraints: device_alert_evaluation_runs ────────
    op.create_check_constraint(
        "ck_eval_runs_trigger_type",
        "device_alert_evaluation_runs",
        sa.text("trigger_type = 'manual'"),
    )
    op.create_check_constraint(
        "ck_eval_runs_status",
        "device_alert_evaluation_runs",
        sa.text(
            "status IN ('running', 'completed', "
            "'completed_with_errors', 'failed')"
        ),
    )
    # All count columns >= 0
    for col in [
        "evaluated_rules_count",
        "created_count",
        "repeated_count",
        "reopened_count",
        "skipped_count",
        "failed_rules_count",
    ]:
        op.create_check_constraint(
            f"ck_eval_runs_{col}_nonneg",
            "device_alert_evaluation_runs",
            sa.text(f"{col} >= 0"),
        )
    # duration_ms nullable but if set must be >= 0
    op.create_check_constraint(
        "ck_eval_runs_duration_nonneg",
        "device_alert_evaluation_runs",
        sa.text("duration_ms IS NULL OR duration_ms >= 0"),
    )

    # ── 4. CHECK constraints: device_alert_evaluation_rule_results
    op.create_check_constraint(
        "ck_eval_rule_results_status",
        "device_alert_evaluation_rule_results",
        sa.text("status IN ('completed', 'skipped', 'failed')"),
    )
    for col in [
        "checked_devices_count",
        "matched_devices_count",
        "created_count",
        "repeated_count",
        "reopened_count",
        "skipped_count",
    ]:
        op.create_check_constraint(
            f"ck_eval_rule_results_{col}_nonneg",
            "device_alert_evaluation_rule_results",
            sa.text(f"{col} >= 0"),
        )


def downgrade() -> None:
    # ── Drop CHECK constraints: runs ─────────────────────────────
    for name in [
        "ck_eval_runs_trigger_type",
        "ck_eval_runs_status",
        "ck_eval_runs_evaluated_rules_count_nonneg",
        "ck_eval_runs_created_count_nonneg",
        "ck_eval_runs_repeated_count_nonneg",
        "ck_eval_runs_reopened_count_nonneg",
        "ck_eval_runs_skipped_count_nonneg",
        "ck_eval_runs_failed_rules_count_nonneg",
        "ck_eval_runs_duration_nonneg",
    ]:
        op.drop_constraint(name, "device_alert_evaluation_runs", type_="check")

    # ── Drop CHECK constraints: rule results ─────────────────────
    for name in [
        "ck_eval_rule_results_status",
        "ck_eval_rule_results_checked_devices_count_nonneg",
        "ck_eval_rule_results_matched_devices_count_nonneg",
        "ck_eval_rule_results_created_count_nonneg",
        "ck_eval_rule_results_repeated_count_nonneg",
        "ck_eval_rule_results_reopened_count_nonneg",
        "ck_eval_rule_results_skipped_count_nonneg",
    ]:
        op.drop_constraint(
            name, "device_alert_evaluation_rule_results", type_="check"
        )

    # ── Revert error_message to TEXT ──────────────────────────────
    op.alter_column(
        "device_alert_evaluation_runs",
        "error_message",
        type_=sa.Text(),
        existing_type=sa.String(500),
        nullable=True,
    )
    op.alter_column(
        "device_alert_evaluation_rule_results",
        "error_message",
        type_=sa.Text(),
        existing_type=sa.String(500),
        nullable=True,
    )
