"""Generated Manifests — test KSO manifest storage.

Revision ID: 029
Create: generated_manifests table for test KSO manifest generation/publishing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("manifest_code", sa.String(64), unique=True, nullable=False),
        sa.Column("device_code", sa.String(64), nullable=False),
        sa.Column("placement_code", sa.String(64), nullable=False),
        sa.Column("campaign_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="generated"),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("manifest_body_json", postgresql.JSONB, nullable=False),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("media_ref_format", sa.String(50), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Indexes
    op.create_index("ix_generated_manifests_manifest_code", "generated_manifests",
                    ["manifest_code"])
    op.create_index("ix_generated_manifests_status", "generated_manifests", ["status"])
    op.create_index("ix_generated_manifests_device_code", "generated_manifests",
                    ["device_code"])

    # FK constraints
    op.create_foreign_key(
        "fk_gm_device_code", "generated_manifests", "kso_devices",
        ["device_code"], ["device_code"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_gm_placement_code", "generated_manifests", "kso_placements",
        ["placement_code"], ["placement_code"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_gm_campaign_code", "generated_manifests", "campaigns",
        ["campaign_code"], ["campaign_code"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_gm_generated_by", "generated_manifests", "users",
        ["generated_by"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_gm_published_by", "generated_manifests", "users",
        ["published_by"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("generated_manifests")
