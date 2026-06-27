"""add scan_status to creatives

Revision ID: 032
Revises: 031_add_reservation_type
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "032_add_scan_status"
down_revision = "031_add_reservation_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "creatives",
        sa.Column(
            "scan_status",
            sa.String(20),
            nullable=False,
            server_default="not_configured",
        ),
    )


def downgrade():
    op.drop_column("creatives", "scan_status")
