"""add_workorder_verifier_id

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-25 10:00:00.000000

工单验收记录补全 (maint-spec §2.2 站长确认/评分)：
- work_orders 增加 verifier_id（独立验收端点记录验收人）
- work_order_ratings 增加 verifier_id（一站式验收记录验收人快照）

用 batch_alter_table 兼容 SQLite（重建表以加 FK）与 PostgreSQL。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (inspector.has_table('work_orders') and inspector.has_table('work_order_ratings')):
        # 表缺失(单表隔离库) -> 优雅跳过
        return

    if not _has_column(bind, 'work_orders', 'verifier_id'):
        with op.batch_alter_table('work_orders') as batch_op:
            batch_op.add_column(sa.Column('verifier_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_work_orders_verifier_id_users', 'users',
                ['verifier_id'], ['id'])

    if not _has_column(bind, 'work_order_ratings', 'verifier_id'):
        with op.batch_alter_table('work_order_ratings') as batch_op:
            batch_op.add_column(sa.Column('verifier_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_work_order_ratings_verifier_id_users', 'users',
                ['verifier_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (inspector.has_table('work_orders') and inspector.has_table('work_order_ratings')):
        # 表缺失 -> 无列可删, 优雅跳过
        return

    if _has_column(bind, 'work_order_ratings', 'verifier_id'):
        with op.batch_alter_table('work_order_ratings') as batch_op:
            batch_op.drop_constraint('fk_work_order_ratings_verifier_id_users', type_='foreignkey')
            batch_op.drop_column('verifier_id')

    if _has_column(bind, 'work_orders', 'verifier_id'):
        with op.batch_alter_table('work_orders') as batch_op:
            batch_op.drop_constraint('fk_work_orders_verifier_id_users', type_='foreignkey')
            batch_op.drop_column('verifier_id')
