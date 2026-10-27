"""fix schema drift: 1 missing column + 10 missing indexes

Revision ID: c4b8e2f9a1d0
Revises: a9b1c2d3e4f5
Create Date: 2026-08-12 00:00:00.000000

修复 2026-08 部署漂移检测报告 (scripts/check_schema_drift.py) 遗留两项:
1 缺列 + 10 缺索引。根因同 9a3c7e1f4d82 / f5a6b7c8d9e0: 涉及表均由
Base.metadata.create_all() 在运行时建表 (不在 baseline migration 内),
create_all checkfirst 只建表不补后续模型新增的列/索引, 故生产旧库长期缺。
本迁移幂等补齐, 让库与模型 metadata 对齐。

检测机制 (check_schema_drift.detect_drift):
- 缺列: model_cols - db_cols
- 缺索引: {idx.name for idx in table.indexes} - db_idx (PK / unique 约束自动
  索引名算库里有)。即只比对「模型显式声明 (含 Column(index=True) 自动生成
  的 ix_<table>_<col>) 的索引名」是否存在。

逐条核对 (写前已 import 全部模型实测 metadata.indexes 确认 unique 属性):

  [缺列]
  enterprise_recharge_applications.approve_reason
    model: enterprise_recharge.py:30 Column(String(500), nullable=True)
    无 default/server_default, nullable 列加列无需 server_default。
    (历史迁移 0f669acebada 注释提及该表漂移但明确「已剔除留待单独清理」, 未加列。)

  [缺索引] name / table / cols / unique
  parking_integration_configs:
    ix_parking_integration_configs_app_key       app_key       True
    ix_parking_integration_configs_station_id    station_id    False
  parking_discount_applied:
    ix_parking_discount_applied_order_no         order_no      True   (order_no 幂等键)
    ix_parking_discount_applied_plate_number     plate_number  False
    ix_parking_discount_applied_station_id       station_id    False
  edge_gateways:
    ix_edge_gateways_id                          id            False
  station_maintenance_grants:
    ix_station_maintenance_grants_granted_by_team_id    granted_by_team_id   False
    ix_station_maintenance_grants_maintenance_team_id   maintenance_team_id  False
    ix_station_maintenance_grants_station_id            station_id           False
    ix_station_maintenance_grants_status                status               False

⚠ 冗余性说明:
- app_key / order_no: Column(unique=True, index=True) 同时声明, SQLAlchemy
  metadata 期望一个 unique=True 的 ix_* 索引; create_index 须带 unique=True
  才与模型一致 (order_no 唯一性是停车减免幂等键的语义保证, 不可降级)。
- edge_gateways.id: 已是主键 (PK 自带索引), Column(primary_key=True, index=True)
  额外声明 ix_edge_gateways_id 普通索引, 功能冗余, 仅为对齐模型消除漂移告警
  (与 f5a6b7c8d9e0 的 ix_charging_orders_transaction_id 同理)。
- station_maintenance_grants: 各 FK 列同时有 __table_args__ 显式 ix_smg_*
  索引 (库里已有, 不报漂移) 与 index=True 自动 ix_station_maintenance_grants_*
  索引 (本迁移补), 二者独立共存。
生产建议 (PostgreSQL): 大表建索引用 CREATE INDEX CONCURRENTLY 避长锁, 当前用
普通 op.create_index, 涉及表数据量小, 可接受。

幂等可重入: SQLite 不支持 CREATE INDEX IF NOT EXISTS / ADD COLUMN IF NOT EXISTS,
全程用 sa.inspect() 探测列/索引存在性决定建/删, PG / SQLite 双方言一致。
表不存在 (极端旧库未 create_all) 整表跳过不报错。对齐 f5a6b7c8d9e0 / 9a3c7e1f4d82
(inspector 幂等) 风格。

可逆: downgrade 按反序 (先 drop 索引, 再 drop 列), 同样判存守卫。

禁改范围: 仅新增本迁移文件, 不触碰模型 / check_schema_drift / 其他迁移 / 任何源码。
"""
from typing import Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4b8e2f9a1d0"
down_revision: Union[str, Sequence[str], None] = "a9b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 1 缺列: (table, column) ----
_MISSING_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("enterprise_recharge_applications", "approve_reason"),
)

# ---- 10 缺索引: (name, table, columns, unique) — unique 取自模型 metadata 实测 ----
_MISSING_INDEXES: Tuple[Tuple[str, str, Tuple[str, ...], bool], ...] = (
    ("ix_parking_integration_configs_app_key", "parking_integration_configs",
     ("app_key",), True),
    ("ix_parking_integration_configs_station_id", "parking_integration_configs",
     ("station_id",), False),
    ("ix_parking_discount_applied_order_no", "parking_discount_applied",
     ("order_no",), True),
    ("ix_parking_discount_applied_plate_number", "parking_discount_applied",
     ("plate_number",), False),
    ("ix_parking_discount_applied_station_id", "parking_discount_applied",
     ("station_id",), False),
    ("ix_edge_gateways_id", "edge_gateways",
     ("id",), False),
    ("ix_station_maintenance_grants_granted_by_team_id", "station_maintenance_grants",
     ("granted_by_team_id",), False),
    ("ix_station_maintenance_grants_maintenance_team_id", "station_maintenance_grants",
     ("maintenance_team_id",), False),
    ("ix_station_maintenance_grants_station_id", "station_maintenance_grants",
     ("station_id",), False),
    ("ix_station_maintenance_grants_status", "station_maintenance_grants",
     ("status",), False),
)


# ---------- helpers ----------

def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in sa.inspect(bind).get_indexes(table)}


# ---------- migration ----------

def upgrade() -> None:
    """幂等补齐 1 缺列 + 10 缺索引 (已存在则跳过)。"""
    bind = op.get_bind()

    # 1. 补缺列 (nullable, 无 server_default)。
    for table, column in _MISSING_COLUMNS:
        if _has_table(bind, table) and not _has_column(bind, table, column):
            op.add_column(table, sa.Column(column, sa.String(length=500), nullable=True))

    # 2. 补缺索引。
    for name, table, columns, unique in _MISSING_INDEXES:
        if _has_table(bind, table) and not _has_index(bind, table, name):
            op.create_index(name, table, list(columns), unique=unique)


def downgrade() -> None:
    """反序: 先 drop 索引, 再 drop 列 (判存守卫)。"""
    bind = op.get_bind()

    for name, table, columns, unique in reversed(_MISSING_INDEXES):
        if _has_table(bind, table) and _has_index(bind, table, name):
            op.drop_index(name, table_name=table)

    for table, column in reversed(_MISSING_COLUMNS):
        if _has_table(bind, table) and _has_column(bind, table, column):
            op.drop_column(table, column)
