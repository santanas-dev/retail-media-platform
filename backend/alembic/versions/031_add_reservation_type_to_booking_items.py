"""add reservation_type to booking_items

Revision ID: 031
Revises: 030_kso_proof_of_play_events
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "031_add_reservation_type"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "booking_items",
        sa.Column(
            "reservation_type",
            sa.String(20),
            nullable=False,
            server_default="campaign",
        ),
    )


def downgrade():
    op.drop_column("booking_items", "reservation_type")
