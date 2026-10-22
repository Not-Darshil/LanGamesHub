"""room chat and emoji reactions

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 18:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'room_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('nickname', sa.String(length=20), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('body', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['player_sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_room_messages_room_id', 'room_messages', ['room_id'])


def downgrade() -> None:
    op.drop_index('ix_room_messages_room_id', table_name='room_messages')
    op.drop_table('room_messages')
