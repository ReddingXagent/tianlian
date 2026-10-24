"""add hot log/flow table fk indexes (card 3839b256)

Revision ID: m9a0b1c2d3e4
Revises: 202608220900
Create Date: 2026-08-26 00:00:00.000000

DB 热点表索引缺失修复 (卡 3839b256)。

前置审计结论(与 765db93fa1b2 同套路, 先实测再动手):
- 模型层大部分热点列已有 index=True 或 __table_args__ 复合索引覆盖,
  真正缺失且热路径已坐实的仅 2 项:
  1. telemetry 复合索引 ix_telemetry_device_ts (device_id, timestamp)
     热路径: app/tasks/analytics_tasks.py:71 + maintenance_tasks.py:114
     逐设备时间窗查询, 单列 ix_telemetry_device_id 需回表再过滤 timestamp
  2. enterprise_transactions.enterprise_id 单列索引
     热路径: app/api/v1/enterprise_transactions.py:70 等 4 端点按企业过滤;
     已有复合 idx_et_enterprise(enterprise_id) 以 enterprise_id 为前缀,
     但为对齐模型层 index=True 声明, 按 SQLAlchemy 约定补
     ix_enterprise_transactions_enterprise_id(单独单列索引, planner 二选一)
     —— 模型层已加 index=True, 缺迁移会导致 create_all 新库与存量库 schema 漂移

其余卡面清单项(telemetry_v2 三表 / api_request_logs / device_health_records /
device_efficiency_logs / occupancy_events / fund_pool_transactions /
device_control_logs / enterprise_transactions.vehicle_id)实测均已有索引, 不重复建。

只追加不重构: 不触碰既有迁移链的 create_all 重复定义问题(另有决策卡)。
幂等: 已有同名索引则跳过, 与 765db93fa1b2 / f5a6b7c8d9e0 同约定。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "202608220900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, [columns])
_INDEXES: list[tuple[str, str, list[str]]] = [
    # 逐设备时间窗查询复合索引
    ("ix_telemetry_device_ts", "telemetry", ["device_id", "timestamp"]),
    # 企业流水按企业过滤(对齐模型 index=True, 防新库/存量库漂移)
    ("ix_enterprise_transactions_enterprise_id", "enterprise_transactions", ["enterprise_id"]),
]


def upgrade() -> None:
    """Upgrade schema: 幂等补齐热点表索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for idx_name, table, columns in _INDEXES:
        if not inspector.has_table(table):
            # 表尚未创建(create_all 按最新模型建, 已含索引) -> 跳过
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        if idx_name not in existing:
            op.create_index(idx_name, table, columns)


def downgrade() -> None:
    """Downgrade schema: 幂等移除本次新增索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for idx_name, table, columns in _INDEXES:
        if not inspector.has_table(table):
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        if idx_name in existing:
            op.drop_index(idx_name, table_name=table)
