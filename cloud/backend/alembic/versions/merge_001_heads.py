"""merge_heads

Revision ID: merge_001
Revises: c3d4e5f6a7b8, c7d8e9f0a1b2
Create Date: 2026-07-23 22:50:00.000000

Merge the two branch heads into a single head:
- c3d4e5f6a7b8 (enterprise owner_team + stations)
- c7d8e9f0a1b2 (invoice platform configs)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "merge_001"
down_revision: Union[str, Sequence[str], None] = ("c3d4e5f6a7b8", "c7d8e9f0a1b2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration - no schema changes."""
    pass


def downgrade() -> None:
    """Merge migration - no schema changes."""
    pass
