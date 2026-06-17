"""Add Manifest & Publication Core.

Revision ID: 009
Revises: 008
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── publication_batches ────────────────────────────────────────
    op.create_table(
        "publication_batches",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "schedule_run_id", UUID(as_uuid=True),
            sa.ForeignKey("schedule_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id", UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id", UUID(as_uuid=True),
            sa.ForeignKey("campaign_bookings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("comment", sa.Text),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "approved_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "published_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "cancelled_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_check_constraint(
        "ck_pub_batches_status",
        "publication_batches",
        sa.text(
            "status IN ('draft','generated','approved','published','failed','cancelled')"
        ),
    )

    op.create_index(
        "ix_pub_batches_schedule_run",
        "publication_batches",
        ["schedule_run_id"],
    )
    op.create_index(
        "ix_pub_batches_campaign",
        "publication_batches",
        ["campaign_id"],
    )
    op.create_index(
        "ix_pub_batches_booking",
        "publication_batches",
        ["booking_id"],
    )
    op.create_index(
        "ix_pub_batches_status",
        "publication_batches",
        ["status"],
    )

    # ── publication_targets ─────────────────────────────────────────
    op.create_table(
        "publication_targets",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "publication_batch_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "inventory_unit_id", UUID(as_uuid=True),
            sa.ForeignKey("inventory_units.id", ondelete="RESTRICT"),
            nullable=False,
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
        "ck_pub_targets_status",
        "publication_targets",
        sa.text(
            "status IN ('pending','generated','published','failed','cancelled')"
        ),
    )

    op.create_unique_constraint(
        "uq_pt_batch_inventory",
        "publication_targets",
        ["publication_batch_id", "inventory_unit_id"],
    )

    op.create_index(
        "ix_pub_targets_batch",
        "publication_targets",
        ["publication_batch_id"],
    )

    # ── manifest_versions ───────────────────────────────────────────
    op.create_table(
        "manifest_versions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "publication_batch_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "publication_target_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_targets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("manifest_version", sa.Integer, nullable=False),
        sa.Column("manifest_json", JSONB, nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(512), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )

    op.create_check_constraint(
        "ck_mv_status",
        "manifest_versions",
        sa.text("status IN ('draft','approved','published','cancelled')"),
    )

    op.create_unique_constraint(
        "uq_mv_target_version",
        "manifest_versions",
        ["publication_target_id", "manifest_version"],
    )

    op.create_index(
        "ix_mv_batch",
        "manifest_versions",
        ["publication_batch_id"],
    )
    op.create_index(
        "ix_mv_target",
        "manifest_versions",
        ["publication_target_id"],
    )

    # ── manifest_items ──────────────────────────────────────────────
    op.create_table(
        "manifest_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "manifest_version_id", UUID(as_uuid=True),
            sa.ForeignKey("manifest_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "schedule_item_id", UUID(as_uuid=True),
            sa.ForeignKey("schedule_items.id", ondelete="RESTRICT"),
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
        sa.Column(
            "creative_version_id", UUID(as_uuid=True),
            sa.ForeignKey("creative_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("media_path", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("time_from", sa.Time, nullable=False),
        sa.Column("time_to", sa.Time, nullable=False),
        sa.Column("loop_position", sa.Integer, nullable=False),
        sa.Column("spot_position", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_mi_manifest_version",
        "manifest_items",
        ["manifest_version_id"],
    )
    op.create_index(
        "ix_mi_schedule_item",
        "manifest_items",
        ["schedule_item_id"],
    )

    # ── publication_events ──────────────────────────────────────────
    op.create_table(
        "publication_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "publication_batch_id", UUID(as_uuid=True),
            sa.ForeignKey("publication_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(30),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
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
        "ck_pub_events_type",
        "publication_events",
        sa.text(
            "event_type IN ("
            "'batch_created','manifest_generated','manifest_generation_failed',"
            "'batch_approved','batch_published','batch_cancelled',"
            "'validation_failed'"
            ")",
        ),
    )

    op.create_index(
        "ix_pub_events_batch",
        "publication_events",
        ["publication_batch_id"],
    )


def downgrade() -> None:
    op.drop_table("publication_events")
    op.drop_table("manifest_items")
    op.drop_table("manifest_versions")
    op.drop_table("publication_targets")
    op.drop_table("publication_batches")
