"""Add media library: creatives, creative_versions, renditions, rendition_validations.

Revision ID: 005
Revises: 004
Create Date: 2026-06-16

Creates:
  - creatives
  - creative_versions
  - renditions
  - rendition_validations
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── creatives ──────────────────────────────────────────────────
    op.create_table(
        "creatives",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("advertiser_id", UUID(as_uuid=True),
                  sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("brands.id", ondelete="RESTRICT"),
                  nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="draft"),
        sa.Column("comment", sa.Text),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── creative_versions ──────────────────────────────────────────
    op.create_table(
        "creative_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("creative_id", UUID(as_uuid=True),
                  sa.ForeignKey("creatives.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("creative_id", "version",
                            name="uq_cv_creative_version"),
    )

    # ── renditions ─────────────────────────────────────────────────
    op.create_table(
        "renditions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("creative_version_id", UUID(as_uuid=True),
                  sa.ForeignKey("creative_versions.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("channel_id", UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("capability_profile_id", UUID(as_uuid=True),
                  sa.ForeignKey("capability_profiles.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── rendition_validations ──────────────────────────────────────
    op.create_table(
        "rendition_validations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.func.gen_random_uuid()),
        sa.Column("rendition_id", UUID(as_uuid=True),
                  sa.ForeignKey("renditions.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("check_type", sa.String(50), nullable=False),
        sa.Column("result", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("details_json", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("checked_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("rendition_validations")
    op.drop_table("renditions")
    op.drop_table("creative_versions")
    op.drop_table("creatives")
