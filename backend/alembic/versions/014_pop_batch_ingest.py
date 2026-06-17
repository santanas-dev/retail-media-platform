"""014_pop_batch_ingest

Revision ID: 014
Revises: 013
Create Date: 2026-06-17

Add proof_of_play_batches table, batch_id FK in proof_of_play_events,
and extend device_events.event_type CHECK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── proof_of_play_batches ─────────────────────────────────────
    op.create_table(
        "proof_of_play_batches",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("device_batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "total_events", sa.Integer(), nullable=False,
        ),
        sa.Column(
            "accepted_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "duplicate_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "rejected_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("batch_status", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "details_json", sa.dialects.postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── Constraints ───────────────────────────────────────────────
    op.create_unique_constraint(
        "uq_device_batch",
        "proof_of_play_batches",
        ["gateway_device_id", "device_batch_id"],
    )
    op.create_check_constraint(
        "ck_pop_batch_total_events",
        "proof_of_play_batches",
        sa.text("total_events >= 0"),
    )
    op.create_check_constraint(
        "ck_pop_batch_accepted_count",
        "proof_of_play_batches",
        sa.text("accepted_count >= 0"),
    )
    op.create_check_constraint(
        "ck_pop_batch_duplicate_count",
        "proof_of_play_batches",
        sa.text("duplicate_count >= 0"),
    )
    op.create_check_constraint(
        "ck_pop_batch_rejected_count",
        "proof_of_play_batches",
        sa.text("rejected_count >= 0"),
    )
    op.create_check_constraint(
        "ck_pop_batch_sum_counts",
        "proof_of_play_batches",
        sa.text(
            "(accepted_count + duplicate_count + rejected_count) = total_events"
        ),
    )
    op.create_check_constraint(
        "ck_pop_batch_status",
        "proof_of_play_batches",
        sa.text(
            "batch_status IN ('processed','partially_processed','rejected')"
        ),
    )

    # ── Indexes ───────────────────────────────────────────────────
    op.create_index(
        "ix_pop_batches_device_id",
        "proof_of_play_batches", ["gateway_device_id"],
    )
    op.create_index(
        "ix_pop_batches_device_batch_id",
        "proof_of_play_batches", ["device_batch_id"],
    )
    op.create_index(
        "ix_pop_batches_status",
        "proof_of_play_batches", ["batch_status"],
    )
    op.create_index(
        "ix_pop_batches_created_at",
        "proof_of_play_batches", ["created_at"],
    )
    op.create_index(
        "ix_pop_batches_device_created",
        "proof_of_play_batches",
        ["gateway_device_id", "created_at"],
    )

    # ── batch_id on proof_of_play_events ──────────────────────────
    op.add_column(
        "proof_of_play_events",
        sa.Column(
            "batch_id", UUID(as_uuid=True),
            sa.ForeignKey("proof_of_play_batches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_pop_batch_id",
        "proof_of_play_events", ["batch_id"],
    )

    # ── Expand device_events.event_type CHECK ─────────────────────
    op.execute("ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type")
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
            "'media_forbidden','media_validation_failed','media_storage_error',"
            "'pop_event_accepted','pop_event_duplicate','pop_event_rejected',"
            "'pop_batch_processed','pop_batch_duplicate','pop_batch_rejected'"
            ")"
        ),
    )


def downgrade() -> None:
    # batch_id index + column
    op.drop_index("ix_pop_batch_id", table_name="proof_of_play_events")
    op.drop_column("proof_of_play_events", "batch_id")

    # proof_of_play_batches indexes
    op.drop_index("ix_pop_batches_device_created", table_name="proof_of_play_batches")
    op.drop_index("ix_pop_batches_created_at", table_name="proof_of_play_batches")
    op.drop_index("ix_pop_batches_status", table_name="proof_of_play_batches")
    op.drop_index("ix_pop_batches_device_batch_id", table_name="proof_of_play_batches")
    op.drop_index("ix_pop_batches_device_id", table_name="proof_of_play_batches")

    op.drop_table("proof_of_play_batches")

    # Restore old CHECK (013's list, without pop_batch_*)
    op.execute("ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type")
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
            "'media_forbidden','media_validation_failed','media_storage_error',"
            "'pop_event_accepted','pop_event_duplicate','pop_event_rejected'"
            ")"
        ),
    )
