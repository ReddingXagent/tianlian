"""add partial unique index uq_et_enterprise_type_order (card 4d3ea0ed)

Revision ID: 202610051200
Revises: 202609272130
Create Date: 2026-10-05 12:00:00.000000

企业交易表 order_id 幂等约束 (卡 4d3ea0ed, 资金安全):
(enterprise_id, type, order_id) 部分唯一索引, order_id IS NOT NULL 时生效,
杜绝网络重试/重复提交同 order_id 的 recharge/refund 重复写流水双倍加余额。
order_id 为 NULL 不受约束 (对齐 charging_order.transaction_id 语义)。

幂等: 已有同名索引则跳过。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610051200"
down_revision: Union[str, None] = "202609272130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDX_NAME = "uq_et_enterprise_type_order"
_TABLE = "enterprise_transactions"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        # 单表隔离库(stamp 后 upgrade head)表不存在 -> 优雅跳过
        return
    existing = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _IDX_NAME in existing:
        return
    op.create_index(
        _IDX_NAME,
        _TABLE,
        ["enterprise_id", "type", "order_id"],
        unique=True,
        sqlite_where=sa.text("order_id IS NOT NULL"),
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        # 表不存在 -> 无索引可删, 优雅跳过
        return
    existing = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _IDX_NAME in existing:
        op.drop_index(_IDX_NAME, table_name=_TABLE)
