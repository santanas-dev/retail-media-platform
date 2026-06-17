"""Add scheduling core: schedule_runs, schedule_items, schedule_conflicts.

Revision ID: 008
Revises: 007
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── schedule_runs ────────────────────────────────────────────
    op.create_table(
        "schedule_runs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "booking_id", UUID(as_uuid=True),
            sa.ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
            nullable=False, index=True,
        ),
        sa.Column(
            "campaign_id", UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(32), nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "generated_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "approved_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── schedule_items ───────────────────────────────────────────
    op.create_table(
        "schedule_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "schedule_run_id", UUID(as_uuid=True),
            sa.ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
            nullable=False, index=True,
        ),
        sa.Column(
            "booking_item_id", UUID(as_uuid=True),
            sa.ForeignKey("booking_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "inventory_unit_id", UUID(as_uuid=True),
            sa.ForeignKey("inventory_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id", UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "campaign_rendition_id", UUID(as_uuid=True),
            sa.ForeignKey("campaign_renditions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rendition_id", UUID(as_uuid=True),
            sa.ForeignKey("renditions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("time_from", sa.Time, nullable=False),
        sa.Column("time_to", sa.Time, nullable=False),
        sa.Column("loop_position", sa.Integer, nullable=False),
        sa.Column("spot_position", sa.Integer, nullable=False),
        sa.Column("spot_duration_seconds", sa.Integer, nullable=False),
        sa.Column("priority", sa.Integer, server_default=sa.text("0")),
        sa.Column("weight", sa.Integer, server_default=sa.text("1")),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── schedule_conflicts ───────────────────────────────────────
    op.create_table(
        "schedule_conflicts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "schedule_run_id", UUID(as_uuid=True),
            sa.ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
            nullable=False, index=True,
        ),
        sa.Column(
            "inventory_unit_id", UUID(as_uuid=True),
            sa.ForeignKey("inventory_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "booking_item_id", UUID(as_uuid=True),
            sa.ForeignKey("booking_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("conflict_type", sa.String(50), nullable=False),
        sa.Column(
            "severity", sa.String(20), nullable=False,
            server_default="error",
        ),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "details_json", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── CHECK constraints ────────────────────────────────────────
    op.create_check_constraint(
        "ck_sr_status", "schedule_runs",
        "status IN ('draft', 'generated', 'has_conflicts', 'approved', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_si_times", "schedule_items",
        "time_from < time_to",
    )
    op.create_check_constraint(
        "ck_si_duration", "schedule_items",
        "spot_duration_seconds > 0",
    )
    op.create_check_constraint(
        "ck_si_loop_pos", "schedule_items",
        "loop_position >= 0",
    )
    op.create_check_constraint(
        "ck_si_spot_pos", "schedule_items",
        "spot_position >= 0",
    )
    op.create_check_constraint(
        "ck_si_status", "schedule_items",
        "status IN ('active', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_sc_type", "schedule_conflicts",
        "conflict_type IN ("
        "'capacity_exceeded', 'missing_capacity_rule', 'invalid_rendition', "
        "'channel_mismatch', 'target_mismatch', 'date_out_of_range', "
        "'no_available_slot', 'invalid_capacity_rule', "
        "'too_many_schedule_items', 'slot_conflict'"
        ")",
    )
    op.create_check_constraint(
        "ck_sc_severity", "schedule_conflicts",
        "severity IN ('warning', 'error', 'blocker')",
    )

    # ── INDEXes ──────────────────────────────────────────────────
    op.create_index(
        "ix_schedule_items_date_unit", "schedule_items",
        ["date", "inventory_unit_id"],
    )
    op.create_index(
        "ix_schedule_items_run", "schedule_items",
        ["schedule_run_id"],
    )
    op.create_index(
        "ix_schedule_conflicts_run", "schedule_conflicts",
        ["schedule_run_id"],
    )


def downgrade() -> None:
    op.drop_table("schedule_conflicts")
    op.drop_table("schedule_items")
    op.drop_table("schedule_runs")
