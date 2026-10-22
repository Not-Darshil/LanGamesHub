"""sound controls, match standings and final states

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('player_sessions', sa.Column('sound_enabled', sa.Boolean(), nullable=True))
    op.add_column('player_sessions', sa.Column('sound_muted_by_host', sa.Boolean(),
                                               server_default='false', nullable=False))
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.add_column('match_results', sa.Column('standings', postgresql.JSONB(astext_type=sa.Text()),
                                             server_default='[]', nullable=False))
    op.add_column('match_results', sa.Column('final_state',
                                             postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('match_results', 'final_state')
    op.drop_column('match_results', 'standings')
    op.drop_table('app_settings')
    op.drop_column('player_sessions', 'sound_muted_by_host')
    op.drop_column('player_sessions', 'sound_enabled')
