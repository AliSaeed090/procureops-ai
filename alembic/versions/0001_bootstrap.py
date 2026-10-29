"""Initial migration baseline; domain tables are added in the data-model implementation issue.

Revision ID: 0001_bootstrap
Revises:
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_bootstrap"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty: establishes migration infrastructure before domain models land.
    pass


def downgrade() -> None:
    pass
