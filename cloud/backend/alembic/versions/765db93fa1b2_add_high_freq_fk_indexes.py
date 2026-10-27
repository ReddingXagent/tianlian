"""add high-frequency fk indexes (audit card 765db93f)

Revision ID: 765db93fa1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-07-31 02:30:00.000000

FK 索引审计补全 (工作板卡 765db93f, GAP-D4)。

PostgreSQL 不自动为 ForeignKey 建索引; 本次审计枚举 app/models 下 45 个
未声明 index=True 的 FK 列(已排除 unique=True / primary_key), 逐条核查
同表 __table_args__ 复合索引覆盖与 app/ 业务代码查询热度后, 锁定 7 个
「真无索引 + 有查询热度」的 FK 补 index=True + 本迁移幂等建索引。

覆盖/冷字段判定见交付清单; 此处只对高频查询路径补索引。

明细 (表.列 -> 查询热度证据):
- knowledge_articles.author_id
    app/api/v1/knowledge.py:520 outerjoin(User, KnowledgeArticle.author_id==User.id)
    知识库全文搜索核心 JOIN (取 author 名称)
- repair_guides.fault_code_id
    app/api/v1/fault_diagnosis.py:106 filter(RepairGuide.fault_code_id==fc.id)
    故障码详情按 fault_code_id 检索关联修复指南
- stations.team_id
    app/api/deps.py:149/152/178/254 归属鉴权 db.query(Station.team_id)
    app/api/v1/v2g.py:176 / efficiency.py:68/181/235 filter(Station.team_id==...)
    多租户团队隔离高频路径
- inspection_tasks.plan_id
    app/api/v1/inspection.py:380 filter(InspectionTask.plan_id==plan_id)
- inspection_tasks.station_id
    app/api/v1/inspection.py:382 filter(InspectionTask.station_id==station_id)
- inspection_plans.team_id
    app/api/v1/inspection.py:210/212 filter(InspectionPlan.team_id==scope/team_id)
    巡检计划团队隔离
- enterprise_transactions.vehicle_id
    app/api/v1/enterprise_vehicles.py:464 EnterpriseTransaction.vehicle_id==vehicle.id
    单车详情聚合查流水

背景: 模型层已为上述 7 列加 index=True, 但 baseline 0001 用
Base.metadata.create_all() 在运行时建表 —— 建于本次改动之前的持久库
(开发 SQLite / 生产 Postgres) 仍缺这些索引, 高频过滤/JOIN 走全表扫描。
本 migration 幂等补齐(已有则跳过), 与 0f669acebada / f5a6b7c8d9e0
保持同一 idempotent 约定。索引名按 SQLAlchemy 约定为 ix_<table>_<column>,
与 create_all 对 index=True 自动生成的命名一致。

禁改范围: 仅新增本迁移文件 + 模型层 index=True 声明, 不触碰 app/api 业务代码 /
其他迁移 / 任何源码逻辑。

可逆: downgrade 按对称幂等移除本次新增索引。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "765db93fa1b2"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) —— 索引名按 SQLAlchemy 约定为 ix_<table>_<column>
_INDEXES: list[tuple[str, str]] = [
    # 知识库全文搜索 JOIN
    ("knowledge_articles", "author_id"),
    # 故障码详情检索
    ("repair_guides", "fault_code_id"),
    # 多租户团队隔离高频路径
    ("stations", "team_id"),
    # 巡检任务列表筛选 + 巡检计划团队隔离
    ("inspection_tasks", "plan_id"),
    ("inspection_tasks", "station_id"),
    ("inspection_plans", "team_id"),
    # 单车流水聚合
    ("enterprise_transactions", "vehicle_id"),
]


def upgrade() -> None:
    """Upgrade schema: 幂等补齐 7 个高频 FK 索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, column in _INDEXES:
        if not inspector.has_table(table):
            # 表尚未创建(create_all 会按最新模型建, 已含索引) -> 跳过
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_{column}"
        if idx_name not in existing_indexes:
            op.create_index(idx_name, table, [column])


def downgrade() -> None:
    """Downgrade schema: 幂等移除本次新增索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, column in _INDEXES:
        if not inspector.has_table(table):
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_{column}"
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name=table)
