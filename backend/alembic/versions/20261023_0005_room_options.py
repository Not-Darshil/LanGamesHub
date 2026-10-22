"""room options (e.g. chess time control)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('rooms', sa.Column('options', postgresql.JSONB(astext_type=sa.Text()),
                                     server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('rooms', 'options')
