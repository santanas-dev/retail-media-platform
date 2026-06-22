"""Add approval_requests table for test KSO approval gate (Step 37.6).

Revision ID: 028
Revises: 027
Create Date: 2026-06-22

- CREATE TABLE approval_requests: minimal approval for campaign/placement.
  Uses stable object_code (not raw UUID).  Maker-checker enforced in service.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "approval_code",
            sa.String(64),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "object_type",
            sa.String(20),
            nullable=False,
        ),
        sa.Column(
            "object_code",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "decision",
            sa.String(20),
            nullable=True,
        ),
        sa.Column(
            "comment",
            sa.String(500),
            nullable=True,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
    op.create_index("ix_approval_code", "approval_requests", ["approval_code"])
    op.create_index("ix_approval_object", "approval_requests", ["object_type", "object_code"])
    op.create_index("ix_approval_status", "approval_requests", ["status"])

    # One active pending per object_type + object_code
    op.create_index(
        "ix_approval_active_pending",
        "approval_requests",
        ["object_type", "object_code", "status"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
