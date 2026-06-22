"""KSO Proof of Play Events — test KSO technical validation.

Revision ID: 030
Create: kso_proof_of_play_events table for test KSO PoP ingest.

NOT the enterprise PoP model — enterprise PoP is proof_of_play_events
+ proof_of_play_batches (migrations 013, 014).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kso_proof_of_play_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_code", sa.String(128), unique=True, nullable=False),
        sa.Column("device_code", sa.String(64), nullable=False),
        sa.Column("placement_code", sa.String(64), nullable=False),
        sa.Column("campaign_code", sa.String(64), nullable=False),
        sa.Column("creative_code", sa.String(64), nullable=False),
        sa.Column("manifest_code", sa.String(64), nullable=False),
        sa.Column("media_ref", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False,
                  server_default="impression"),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="accepted"),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Indexes
    op.create_index("ix_kso_pop_event_code", "kso_proof_of_play_events",
                    ["event_code"])
    op.create_index("ix_kso_pop_device_code", "kso_proof_of_play_events",
                    ["device_code"])
    op.create_index("ix_kso_pop_placement_code", "kso_proof_of_play_events",
                    ["placement_code"])
    op.create_index("ix_kso_pop_campaign_code", "kso_proof_of_play_events",
                    ["campaign_code"])
    op.create_index("ix_kso_pop_creative_code", "kso_proof_of_play_events",
                    ["creative_code"])
    op.create_index("ix_kso_pop_manifest_code", "kso_proof_of_play_events",
                    ["manifest_code"])
    op.create_index("ix_kso_pop_status", "kso_proof_of_play_events",
                    ["status"])

    # FK constraints — all RESTRICT
    op.create_foreign_key(
        "fk_kso_pop_device_code", "kso_proof_of_play_events",
        "kso_devices", ["device_code"], ["device_code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_kso_pop_placement_code", "kso_proof_of_play_events",
        "kso_placements", ["placement_code"], ["placement_code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_kso_pop_campaign_code", "kso_proof_of_play_events",
        "campaigns", ["campaign_code"], ["campaign_code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_kso_pop_creative_code", "kso_proof_of_play_events",
        "creatives", ["creative_code"], ["creative_code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_kso_pop_manifest_code", "kso_proof_of_play_events",
        "generated_manifests", ["manifest_code"], ["manifest_code"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_table("kso_proof_of_play_events")
