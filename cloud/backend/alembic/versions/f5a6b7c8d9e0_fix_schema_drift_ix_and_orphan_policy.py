"""fix schema drift: ix_charging_orders_transaction_id + drop reservation_fee_prices.policy

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-28 19:30:00.000000

修复 7-28 部署漂移检测报告 (deploy_20260728_182308.log) 遗留两项:

1. [缺索引] charging_orders.ix_charging_orders_transaction_id
   根因: charging_order.py:75 `transaction_id = Column(..., index=True)` 显式
   声明 → SQLAlchemy metadata 期望名为 ix_charging_orders_transaction_id 的
   单列索引。但 charging_orders 由 Base.metadata.create_all() 在运行时建表,
   表先于 transaction_id 字段落地; 后续 e4f5a6b7c8d9 迁移只补了 transaction_id
   列和 idx_co_tx_device(transaction_id, device_id) 复合唯一索引, 漏建这个
   index=True 对应的单列索引。create_all checkfirst 只建表不补索引, 故生产旧库
   长期缺失 → 漂移告警。charging-sessions 幂等/竞态回查按 transaction_id 查询,
   补单列索引加速。

   ⚠ 冗余性: 复合索引 idx_co_tx_device 最左前缀已覆盖 transaction_id 单列查询,
   功能上该单列索引冗余。此处仅为对齐模型 index=True 声明、消除漂移告警。
   若后续要瘦身, 应同时改模型去 index=True 并 drop 本索引, 保持模型/库一致。

   生产建议 (PostgreSQL): 大表建索引用 CREATE INDEX CONCURRENTLY 避免长锁,
   需 op.execute + with op.get_context().autocommit_block(); 当前用普通
   op.create_index, 生产 charging_orders 量小, 可接受。

2. [孤儿列] reservation_fee_prices.policy
   根因: 生产库存在该列, 但模型无 (模型字段为 reservation_policy,
   pricing_v2.py:168)。全仓 grep (app/ + alembic/) 零代码引用, raw SQL 也无
   .policy / "policy" 访问 → 历史遗留 (疑似早期命名 policy, 后改名
   reservation_policy 但未 drop 旧列)。漂移报告标注 "仅报告,不算漂移",
   此处主动 drop 清理, 让库与模型对齐。

   downgrade 恢复该列时类型未知 (漂移报告只给列名), 以 sa.Text() 占位恢复,
   仅供结构回滚, 不保证还原原始类型 (反正无代码引用)。

幂等可重入: 全程用 sa.inspect() 探测表/列/索引存在性决定建/删, PG / SQLite
双方言一致, 表不存在 (极端旧库未 create_all) 整表跳过不报错。对齐 9a3c7e1f4d82
(补生产缺失索引) + e4f5a6b7c8d9 (inspector 幂等) 风格。

可逆: downgrade 按反序恢复 (先恢复 policy 列, 再 drop 单列索引)。

禁改范围: 仅新增本迁移文件, 不触碰模型 / 其他迁移 / 任何源码。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ORDERS_TABLE = "charging_orders"
_RESERV_TABLE = "reservation_fee_prices"
_TX_SINGLE_INDEX = "ix_charging_orders_transaction_id"
_TX_COLUMN = "transaction_id"
_ORPHAN_COLUMN = "policy"


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 补 ix_charging_orders_transaction_id 单列索引。
    #    依赖 transaction_id 列 (由 e4f5a6b7c8d9 拥有); 列不存在则跳过不报错。
    if (
        _has_table(bind, _ORDERS_TABLE)
        and _has_column(bind, _ORDERS_TABLE, _TX_COLUMN)
        and not _has_index(bind, _ORDERS_TABLE, _TX_SINGLE_INDEX)
    ):
        op.create_index(_TX_SINGLE_INDEX, _ORDERS_TABLE, [_TX_COLUMN])

    # 2. drop 孤儿列 reservation_fee_prices.policy (库有模型无, 无代码引用)。
    if _has_table(bind, _RESERV_TABLE) and _has_column(bind, _RESERV_TABLE, _ORPHAN_COLUMN):
        op.drop_column(_RESERV_TABLE, _ORPHAN_COLUMN)


def downgrade() -> None:
    bind = op.get_bind()

    # 反序恢复: 先恢复 policy 列, 再 drop 单列索引。

    # 2'. 恢复孤儿列 policy (原始类型未知, 以 Text 占位恢复结构)。
    if _has_table(bind, _RESERV_TABLE) and not _has_column(bind, _RESERV_TABLE, _ORPHAN_COLUMN):
        op.add_column(_RESERV_TABLE, sa.Column(_ORPHAN_COLUMN, sa.Text(), nullable=True))

    # 1'. drop 单列索引。
    if _has_table(bind, _ORDERS_TABLE) and _has_index(bind, _ORDERS_TABLE, _TX_SINGLE_INDEX):
        op.drop_index(_TX_SINGLE_INDEX, table_name=_ORDERS_TABLE)
