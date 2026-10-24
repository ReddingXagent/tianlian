"""add transaction_id + connector_id to charging_orders (charging-session ingestion)

Revision ID: e4f5a6b7c8d9
Revises: 9a3c7e1f4d82
Create Date: 2026-07-28 10:00:00.000000

为充电交易 ingestion 管道(d018e3dc) 增加幂等锚点:
- charging_orders.transaction_id  外部 OCPP transactionId(可空)
- charging_orders.connector_id    外部 OCPP connectorId(可空)
- UNIQUE (transaction_id, device_id)  幂等: 同一桩同一交易号只建一单

幂等语义: SQL 标准下 UNIQUE 索引对完全为 NULL 的列不约束(NULL != NULL),
故手工建单(transaction_id 恒 NULL)多条共存不受影响; 仅当 transaction_id 非 NULL
时, 同 (transaction_id, device_id) 组合重复上报返回已有订单。

- PG / SQLite 双兼容: 用 inspector 探测列/索引存在性, 幂等可重入。
- 仅加列 + 建索引, 无数据迁移(生产 charging_orders 当前 0 行)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "9a3c7e1f4d82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "charging_orders"
_TX_INDEX = "idx_co_tx_device"


def _has_table(bind) -> bool:
    return _TABLE in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        # 表尚未存在(create_all 会按最新模型建, 已含新列与索引)
        return

    if not _has_column(bind, _TABLE, "transaction_id"):
        op.add_column(_TABLE, sa.Column("transaction_id", sa.String(length=64), nullable=True))
    if not _has_column(bind, _TABLE, "connector_id"):
        op.add_column(_TABLE, sa.Column("connector_id", sa.Integer(), nullable=True))
    if not _has_index(bind, _TABLE, _TX_INDEX):
        op.create_index(_TX_INDEX, _TABLE, ["transaction_id", "device_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return

    if _has_index(bind, _TABLE, _TX_INDEX):
        op.drop_index(_TX_INDEX, table_name=_TABLE)
    if _has_column(bind, _TABLE, "transaction_id"):
        op.drop_column(_TABLE, "transaction_id")
    if _has_column(bind, _TABLE, "connector_id"):
        op.drop_column(_TABLE, "connector_id")
