"""Baseline revision: establishes Alembic version tracking.

Application tables are added by later revisions as each feature lands.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
