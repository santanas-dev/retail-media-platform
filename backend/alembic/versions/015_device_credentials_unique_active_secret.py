"""015_device_credentials_unique_active_secret

Revision ID: 015
Revises: 014
Create Date: 2026-06-17

Enforce single active shared_secret credential per device at DB level.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_device_active_shared_secret",
        "device_credentials",
        ["gateway_device_id"],
        unique=True,
        postgresql_where=(
            "credential_type = 'shared_secret' AND status = 'active'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_device_active_shared_secret",
        table_name="device_credentials",
        postgresql_where=(
            "credential_type = 'shared_secret' AND status = 'active'"
        ),
    )
