"""work_orders: 补 dispatch_type + source 两列 (maint-platform-spec §4)

Revision ID: 202607310600
Revises: 202607310500
Create Date: 2026-07-31 06:00:00.000000

工单派发方式与来源缺口补齐:
- dispatch_type: assign=指派 / grab=抢单 (默认 assign)
- source: manual/alarm/app/inspection (默认 manual)

两列 nullable=False + server_default, 存量行自动回填, 不破坏既有数据。

幂等设计:
- 全新库 (仅走迁移建表): create_all 已含两列 (对齐 model), 本迁移 _has_column 守卫跳过。
- 存量库 (表已存在缺两列): 仅补缺失列。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '202607310600'
down_revision = '202607310500'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table('work_orders'):
        # 表缺失(单表隔离库) -> 优雅跳过
        return
    if not _has_column('work_orders', 'dispatch_type'):
        op.add_column(
            'work_orders',
            sa.Column('dispatch_type', sa.String(length=20), nullable=False, server_default='assign'),
        )
    if not _has_column('work_orders', 'source'):
        op.add_column(
            'work_orders',
            sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'),
        )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table('work_orders'):
        # 表缺失 -> 无列可删, 优雅跳过
        return
    if _has_column('work_orders', 'source'):
        op.drop_column('work_orders', 'source')
    if _has_column('work_orders', 'dispatch_type'):
        op.drop_column('work_orders', 'dispatch_type')
