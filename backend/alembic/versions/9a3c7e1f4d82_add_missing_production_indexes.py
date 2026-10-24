"""add missing production indexes (team scoping + approval)

Revision ID: 9a3c7e1f4d82
Revises: 0658b3b78147
Create Date: 2026-07-28 03:00:00.000000

补齐 5 个生产缺失索引 (全部取自模型 __table_args__, 写前已逐条核对列名/组合):

    idx_msuperteam  ON municipal_supervision_configs(team_id)
                     [app/models/admin_supervision.py:50]
    idx_rreport_team ON regulatory_reports(team_id)
                     [app/models/admin_supervision.py:73]
    idx_cca_team     ON compliance_checks(team_id)
                     [app/models/admin_supervision.py:96]
    idx_iorder_team  ON interconnect_orders(team_id)
                     [app/models/admin_interconnect.py:76]
    idx_ev_approval  ON enterprise_vehicles(enterprise_id, approval_status)
                     [app/models/enterprise_vehicle.py:54]

根因: 与 0658b3b78147 (补缺列) 同源 — municipal_supervision_configs /
regulatory_reports / compliance_checks / interconnect_orders /
enterprise_vehicles 五张表均由 Base.metadata.create_all() 在运行时建表,
不在 baseline migration 内。create_all 只建不补: 表已存在时不会追加模型后续
新增的索引, 故开发 SQLite (早期 create_all 建表) 与生产 Postgres 旧库均缺这
5 个 team_id / approval 复合索引。前序迁移已用同样机制补齐了
interconnect_configs.idx_iconfig_team (见 0658b3b78147._ensure_iconfig_index),
本迁移把剩余 5 个一并补上。

幂等守卫: SQLite 不支持 CREATE INDEX IF NOT EXISTS, 故用 inspector 判存
(has_table + get_indexes) 决定建/删; PG 同样走 inspector 判存, 双方言一致。
表不存在 (极端旧库未 create_all) 则整表跳过, 不报错。

可逆: downgrade 按反序 drop 这 5 个索引, 同样判存 (存在才 drop)。idx_ev_approval
依赖的 approval_status 列由 0658b3b78147 拥有, 仅 downgrade 本迁移时该列仍在,
drop 索引独立安全; 若一路 downgrade 到 base, 0658b3b78147 的 _drop_indexes_referencing
会先于 drop approval_status 列 drop 引用它的索引, 顺序无冲突。

禁改范围: 仅新增本迁移文件, 不触碰模型 / schema_validator / 其他迁移 / 任何源码。
"""
from typing import List, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a3c7e1f4d82"
down_revision: Union[str, Sequence[str], None] = "0658b3b78147"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 5 缺失索引 (name, table, columns) — 取自模型 __table_args__ ----
_MISSING_INDEXES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("idx_msuperteam", "municipal_supervision_configs", ("team_id",)),
    ("idx_rreport_team", "regulatory_reports", ("team_id",)),
    ("idx_cca_team", "compliance_checks", ("team_id",)),
    ("idx_iorder_team", "interconnect_orders", ("team_id",)),
    ("idx_ev_approval", "enterprise_vehicles", ("enterprise_id", "approval_status")),
)


# ---------- helpers ----------

def _ensure_index(name: str, table: str, columns: Sequence[str], create: bool) -> None:
    """幂等建/删单个索引 (inspector 判存守卫)。

    SQLite 不支持 CREATE INDEX IF NOT EXISTS / DROP INDEX IF EXISTS, 用 inspector
    判存代替。表不存在 (旧库未 create_all 该表) 则跳过, 不报错。PG 走同一判存逻辑,
    双方言行为一致。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return
    existing = {i["name"] for i in inspector.get_indexes(table)}
    if create and name not in existing:
        op.create_index(name, table, list(columns))
    elif not create and name in existing:
        op.drop_index(name, table_name=table)


# ---------- migration ----------

def upgrade() -> None:
    """幂等补齐 5 个 team_id / approval 索引 (已存在则跳过)。"""
    for name, table, columns in _MISSING_INDEXES:
        _ensure_index(name, table, columns, create=True)


def downgrade() -> None:
    """反序 drop 这 5 个索引 (存在才 drop, 判存守卫)。"""
    for name, table, columns in reversed(_MISSING_INDEXES):
        _ensure_index(name, table, columns, create=False)
