"""add 23 missing FK column indexes (card ba8f3bb1)

Revision ID: 202610051300
Revises: 202610051200
Create Date: 2026-10-05 13:00:00.000000

FK 列缺索引一致性修复 (卡 ba8f3bb1-5eb8-4454-a3e1-f96d087a1937):
23 处 ForeignKey 列既无 index=True 也无 Index() 覆盖, 与模型补丁一一对应。
生产 PG 下外键列无索引会导致父表 DELETE/UPDATE 回查子表全表扫,
以及「我创建/我处理/我负责」反向列表查询无索引慢。

幂等: 已有同名索引则跳过。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610051300"
down_revision: Union[str, None] = "202610051200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) 对应模型层补 index=True 的 23 列
_FK_INDEXES = [
    ("agent_conversation", "user_id"),
    ("alarms", "handler_id"),
    ("alarm_rule_logs", "alarm_id"),
    ("devices", "gateway_id"),
    ("station_energy_strategy", "price_template_id"),
    ("energy_dispatch_plan", "price_template_id"),
    ("fleet_drivers", "assigned_vehicle_id"),
    ("fleet_recharge_requests", "reviewed_by"),
    ("knowledge_articles", "category_id"),
    ("merchants", "tenant_id"),
    ("notification_logs", "template_id"),
    ("on_call_shifts", "backup_user_id"),
    ("stations", "operator_id"),
    ("teams", "leader_id"),
    ("work_orders", "creator_id"),
    ("work_orders", "verifier_id"),
    ("work_order_logs", "user_id"),
    ("work_order_checkins", "user_id"),
    ("work_order_support_requests", "target_engineer_id"),
    ("work_order_support_requests", "user_id"),
    ("work_order_spare_parts", "user_id"),
    ("work_order_ratings", "user_id"),
    ("work_order_ratings", "verifier_id"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_by_table = {}
    for t, _ in _FK_INDEXES:
        if not inspector.has_table(t):
            # 表缺失(单表隔离库) -> 跳过该表全部索引
            continue
        existing_by_table[t] = {ix["name"] for ix in inspector.get_indexes(t)}
    for table, col in _FK_INDEXES:
        if table not in existing_by_table:
            continue
        name = op.f(f"ix_{table}_{col}")
        if name in existing_by_table[table]:
            continue
        op.create_index(name, table, [col], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_by_table = {}
    for t, _ in _FK_INDEXES:
        if not inspector.has_table(t):
            # 表缺失 -> 无索引可删, 跳过
            continue
        existing_by_table[t] = {ix["name"] for ix in inspector.get_indexes(t)}
    for table, col in _FK_INDEXES:
        if table not in existing_by_table:
            continue
        name = op.f(f"ix_{table}_{col}")
        if name in existing_by_table[table]:
            op.drop_index(name, table_name=table)
