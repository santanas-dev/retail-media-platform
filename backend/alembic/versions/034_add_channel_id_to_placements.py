"""B.3.1 — Add channel_id to placements

Revision ID: 034
Revises: 033
Create Date: 2026-06-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision: str = '034_add_channel_id_to_placements'
down_revision: Union[str, None] = '033_schedules_and_slots'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add nullable channel_id column
    op.add_column('placements',
        sa.Column('channel_id', UUID(as_uuid=True), nullable=True)
    )

    # Step 2: Add FK constraint
    op.create_foreign_key(
        'fk_placements_channel',
        'placements', 'channels',
        ['channel_id'], ['id'],
        ondelete='RESTRICT'
    )

    # Step 3: Add index
    op.create_index('idx_placements_channel', 'placements', ['channel_id'])

    # Step 4: Fill channel_id for existing placements
    # For the test seed placement, use the KSO channel
    op.execute("""
        UPDATE placements
        SET channel_id = (
            SELECT ch.id FROM channels ch WHERE ch.code = 'kso'
        )
        WHERE channel_id IS NULL
    """)

    # Step 5: Verify no NULLs remain (safety check)
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text("SELECT count(*) FROM placements WHERE channel_id IS NULL")
    ).scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Migration 034: {null_count} placements still have NULL channel_id "
            f"after fill. Aborting SET NOT NULL."
        )

    # Step 6: Set NOT NULL
    op.alter_column('placements', 'channel_id', nullable=False)


def downgrade() -> None:
    op.drop_index('idx_placements_channel', table_name='placements')
    op.drop_constraint('fk_placements_channel', 'placements', type_='foreignkey')
    op.drop_column('placements', 'channel_id')
