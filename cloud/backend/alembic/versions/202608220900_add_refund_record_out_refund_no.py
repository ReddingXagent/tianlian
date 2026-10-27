"""add out_refund_no to refund_records (卡 69fe6381 退款幂等键)

Revision ID: 202608220900
Revises: 202608210900
Create Date: 2026-08-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '202608220900'
down_revision: Union[str, Sequence[str], None] = '202608210900'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = 'refund_records'
_COLUMN = 'out_refund_no'
_INDEX = 'ix_refund_records_out_refund_no'


def _existing_cols(inspector) -> set:
    return {c['name'] for c in inspector.get_columns(_TABLE)}


def _existing_indexes(inspector) -> set:
    return {ix['name'] for ix in inspector.get_indexes(_TABLE)}


def upgrade() -> None:
    """Add out_refund_no (unique) to refund_records.

    幂等守卫 (与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    全新库已含此列 → 跳过; 既有库列不存在 → add。重复跑不炸。

    ⚠ 生产库永不重放该迁移 — unique 索引仅对新写入的退款单号生效, 历史空值
    不受影响; 一旦生产已升到此版本, 不得 downgrade+replay (唯一约束下重放
    会因历史数据状态不确定而失败)。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    cols = _existing_cols(inspector)
    if _COLUMN not in cols:
        # unique=True: 先加可空列, 再建唯一索引 (SQLite ALTER 无法带约束)。
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(64), nullable=True,
                      comment='平台退款幂等单号(重试复用)'),
        )
    indexes = _existing_indexes(inspector)
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=True)


def downgrade() -> None:
    """Drop out_refund_no from refund_records."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    if _INDEX in _existing_indexes(inspector):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _existing_cols(inspector):
        op.drop_column(_TABLE, _COLUMN)
