"""charging_orders 补 vehicle_id/plate_number 索引 (卡 57e7b199)

Revision ID: 202608271500
Revises: n0ac1b2d3e4f
Create Date: 2026-08-27 15:00:00.000000

模型 app/models/charging_order.py 的 __table_args__ 已声明两索引, 但迁移链
从未落地 (与卡 71e2f120 的 uq_connector_active_order 同款 drift)。开发 SQLite
由 create_all 建索引故无感, 生产 PG 旧库缺索引 → 多个热点查询全表扫:
- fleet 充电统计: 按 vehicle_id 聚合订单
- 车辆详情订单历史: 按 vehicle_id 过滤
- 占位费重叠单匹配: occupancy_fee_service._find_overlapping_order 按
  plate_number 查重叠订单
- 车牌维度订单查询/报表: 按 plate_number 过滤

两列本身可空且无唯一语义, 普通二级索引即可。幂等守卫: inspector 判存
(SQLite 无 CREATE INDEX IF NOT EXISTS, 见 202608161500 同款机制); 表不存在
(极端旧库) 整跳过。可逆: downgrade 对称 drop。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608271500"
down_revision: Union[str, Sequence[str], None] = "n0ac1b2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "charging_orders"
INDEXES = [
    ("idx_co_vehicle", ["vehicle_id"]),
    ("idx_co_plate", ["plate_number"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    existing = {i["name"] for i in inspector.get_indexes(TABLE)}
    for name, cols in INDEXES:
        if name not in existing:
            op.create_index(name, TABLE, cols)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = {i["name"] for i in inspector.get_indexes(TABLE)}
    for name, _cols in INDEXES:
        if name in existing:
            op.drop_index(name, table_name=TABLE)
