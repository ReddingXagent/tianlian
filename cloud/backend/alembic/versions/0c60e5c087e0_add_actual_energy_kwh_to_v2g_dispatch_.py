"""add actual_energy_kwh to v2g_dispatch_log

Revision ID: 0c60e5c087e0
Revises: 0f669acebada
Create Date: 2026-07-28 02:07:03.145632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c60e5c087e0'
down_revision: Union[str, Sequence[str], None] = '0f669acebada'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = 'v2g_dispatch_logs'
_COLUMN = 'actual_energy_kwh'


def upgrade() -> None:
    """Add actual_energy_kwh to v2g_dispatch_logs.

    幂等守卫 (与 88377de16771/j7e8f9a0b1c2 一致): baseline 用 metadata.create_all
    建表的全新库已含此列 → 跳过; 生产库 (baseline 不重跑) 列不存在 → add。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_cols = {c['name'] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Float(), nullable=True, comment='实际能量(kWh)'),
        )


def downgrade() -> None:
    """Drop actual_energy_kwh from v2g_dispatch_logs."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_cols = {c['name'] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_cols:
        op.drop_column(_TABLE, _COLUMN)
