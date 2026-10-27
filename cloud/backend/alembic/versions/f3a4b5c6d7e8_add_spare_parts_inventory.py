"""add_spare_parts_inventory

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-25 11:00:00.000000

备件库存台账 (maint-platform-spec §2.2):
- spare_parts_inventory: 独立库存表，记录累计入库量(total)与可用量(available)。
  工单申请备件时(workorders.spare_parts_workorder)按 (part_name, part_model)
  匹配本表扣减 available_quantity。

幂等: 用 inspector 判表存在再建，兼容已 create_all 的环境。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, 'spare_parts_inventory'):
        op.create_table(
            'spare_parts_inventory',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('part_name', sa.String(length=100), nullable=False),
            sa.Column('part_model', sa.String(length=100), nullable=True),
            sa.Column('total_quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('available_quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('warehouse', sa.String(length=100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_spare_parts_inventory_id', 'spare_parts_inventory', ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, 'spare_parts_inventory'):
        op.drop_index('ix_spare_parts_inventory_id', table_name='spare_parts_inventory')
        op.drop_table('spare_parts_inventory')
