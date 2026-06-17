"""013_pop_ingest_core

Revision ID: 013
Revises: 012
Create Date: 2026-06-17

Add proof_of_play_events table and extend device_events.event_type CHECK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── proof_of_play_events table ─────────────────────────────────

    op.create_table(
        "proof_of_play_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "gateway_device_id", UUID(as_uuid=True),
            sa.ForeignKey("gateway_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("device_event_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "manifest_item_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_items.id", ondelete="RESTRICT"),
            nullable=True,
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
            "schedule_item_id", UUID(as_uuid=True),
            sa.ForeignKey("schedule_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "campaign_id", UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "campaign_rendition_id", UUID(as_uuid=True),
            sa.ForeignKey("campaign_renditions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "rendition_id", UUID(as_uuid=True),
            sa.ForeignKey("renditions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "creative_version_id", UUID(as_uuid=True),
            sa.ForeignKey("creative_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("play_status", sa.String(20), nullable=True),
        sa.Column(
            "validation_status", sa.String(20), nullable=False,
            server_default="accepted",
        ),
        sa.Column("media_sha256", sa.String(64), nullable=True),
        sa.Column("expected_sha256", sa.String(64), nullable=True),
        sa.Column("player_version", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "details_json", sa.dialects.postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rejection_reason", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── Constraints ─────────────────────────────────────────────────

    op.create_unique_constraint(
        "uq_pop_device_event", "proof_of_play_events",
        ["gateway_device_id", "device_event_id"],
    )
    op.create_check_constraint(
        "ck_pop_play_status", "proof_of_play_events",
        sa.text(
            "play_status IS NULL OR play_status IN "
            "('started','completed','interrupted','skipped','failed')"
        ),
    )
    op.create_check_constraint(
        "ck_pop_validation_status", "proof_of_play_events",
        sa.text(
            "validation_status IN ('accepted','duplicate','rejected')"
        ),
    )
    op.create_check_constraint(
        "ck_pop_media_sha256", "proof_of_play_events",
        sa.text(
            "media_sha256 IS NULL OR media_sha256 ~ '^[a-f0-9]{64}$'"
        ),
    )
    op.create_check_constraint(
        "ck_pop_expected_sha256", "proof_of_play_events",
        sa.text(
            "expected_sha256 IS NULL OR expected_sha256 ~ '^[a-f0-9]{64}$'"
        ),
    )
    op.create_check_constraint(
        "ck_pop_duration_ms", "proof_of_play_events",
        sa.text("duration_ms IS NULL OR duration_ms >= 0"),
    )

    # ── Indexes ─────────────────────────────────────────────────────

    op.create_index("ix_pop_device_id", "proof_of_play_events", ["gateway_device_id"])
    op.create_index("ix_pop_event_id", "proof_of_play_events", ["device_event_id"])
    op.create_index("ix_pop_mi_id", "proof_of_play_events", ["manifest_item_id"])
    op.create_index("ix_pop_mv_id", "proof_of_play_events", ["manifest_version_id"])
    op.create_index("ix_pop_target_id", "proof_of_play_events", ["publication_target_id"])
    op.create_index("ix_pop_campaign_id", "proof_of_play_events", ["campaign_id"])
    op.create_index("ix_pop_si_id", "proof_of_play_events", ["schedule_item_id"])
    op.create_index("ix_pop_validation_status", "proof_of_play_events", ["validation_status"])
    op.create_index("ix_pop_play_status", "proof_of_play_events", ["play_status"])
    op.create_index("ix_pop_played_at", "proof_of_play_events", ["played_at"])
    op.create_index("ix_pop_received_at", "proof_of_play_events", ["received_at"])
    op.create_index("ix_pop_created_at", "proof_of_play_events", ["created_at"])
    op.create_index(
        "ix_pop_device_created", "proof_of_play_events",
        ["gateway_device_id", "created_at"],
    )

    # ── Expand device_events.event_type CHECK ───────────────────────

    op.execute("ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type")
    op.create_check_constraint(
        "ck_de_type", "device_events",
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


def downgrade() -> None:
    op.drop_index("ix_pop_device_created", table_name="proof_of_play_events")
    op.drop_index("ix_pop_created_at", table_name="proof_of_play_events")
    op.drop_index("ix_pop_received_at", table_name="proof_of_play_events")
    op.drop_index("ix_pop_played_at", table_name="proof_of_play_events")
    op.drop_index("ix_pop_play_status", table_name="proof_of_play_events")
    op.drop_index("ix_pop_validation_status", table_name="proof_of_play_events")
    op.drop_index("ix_pop_si_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_campaign_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_target_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_mv_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_mi_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_event_id", table_name="proof_of_play_events")
    op.drop_index("ix_pop_device_id", table_name="proof_of_play_events")
    op.drop_table("proof_of_play_events")

    # Restore old CHECK constraint (012's list)
    op.execute("ALTER TABLE device_events DROP CONSTRAINT IF EXISTS ck_de_type")
    op.create_check_constraint(
        "ck_de_type", "device_events",
        sa.text(
            "event_type IN ("
            "'device_registered','credential_issued','credential_rotated',"
            "'credential_revoked','device_login_success','device_login_failed',"
            "'heartbeat_received','device_disabled','device_reactivated',"
            "'invalid_token','validation_failed',"
            "'manifest_served','manifest_not_modified','manifest_not_found',"
            "'manifest_forbidden',"
            "'media_served','media_not_modified','media_not_found',"
            "'media_forbidden','media_validation_failed','media_storage_error'"
            ")"
        ),
    )
