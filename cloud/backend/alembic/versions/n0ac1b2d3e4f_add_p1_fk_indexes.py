"""add p1 secondary hot table fk indexes (card f1c99ce5)

Revision ID: n0ac1b2d3e4f
Revises: m9a0b1c2d3e4
Create Date: 2026-08-26 00:00:00.000000

DB 索引第2批: P1 次热表 FK 索引补齐 (卡 f1c99ce5)。

模型层这些 FK 列早已声明 index=True (母卡 4b4acaea2 审计确认),
但存量生产库可能从未收到对应迁移 —— 本迁移按 SQLAlchemy 约定名
幂等补齐, 消除 create_all 新库与存量库的 schema 漂移:
- api_request_logs: client_id / api_key_id
- device_health_records / device_control_logs: device_id
- device_efficiency_logs: device_id
- occupancy_events: station_id
- fund_pool_transactions: fund_pool_id (模型另有显式 idx_fund_txn_pool, 两者并存对齐声明)
- enterprise_transactions: vehicle_id
- telemetry_v2 三表 (pv/battery/charger): device_id / station_id
  (另有复合 idx_*_station_device_ts 覆盖, 单列索引按模型声明补齐)

幂等: 已有同名索引则跳过, 与 m9a0b1c2d3e4 同约定。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "n0ac1b2d3e4f"
down_revision: Union[str, Sequence[str], None] = "m9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, [columns])
_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_api_request_logs_client_id", "api_request_logs", ["client_id"]),
    ("ix_api_request_logs_api_key_id", "api_request_logs", ["api_key_id"]),
    ("ix_device_health_records_device_id", "device_health_records", ["device_id"]),
    ("ix_device_efficiency_logs_device_id", "device_efficiency_logs", ["device_id"]),
    ("ix_occupancy_events_station_id", "occupancy_events", ["station_id"]),
    ("ix_fund_pool_transactions_fund_pool_id", "fund_pool_transactions", ["fund_pool_id"]),
    ("ix_device_control_logs_device_id", "device_control_logs", ["device_id"]),
    ("ix_enterprise_transactions_vehicle_id", "enterprise_transactions", ["vehicle_id"]),
    ("ix_telemetry_pv_device_id", "telemetry_pv", ["device_id"]),
    ("ix_telemetry_pv_station_id", "telemetry_pv", ["station_id"]),
    ("ix_telemetry_battery_device_id", "telemetry_battery", ["device_id"]),
    ("ix_telemetry_battery_station_id", "telemetry_battery", ["station_id"]),
    ("ix_telemetry_charger_device_id", "telemetry_charger", ["device_id"]),
    ("ix_telemetry_charger_station_id", "telemetry_charger", ["station_id"]),
]


def upgrade() -> None:
    """Upgrade schema: 幂等补齐 P1 次热表 FK 索引。"""
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

    for idx_name, table, _columns in _INDEXES:
        if not inspector.has_table(table):
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        if idx_name in existing:
            op.drop_index(idx_name, table_name=table)
