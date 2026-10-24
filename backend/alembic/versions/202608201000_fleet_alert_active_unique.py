"""fleet_alert_records active 部分唯一索引 (卡 49aafa24)

Revision ID: 202608201000
Revises: 202608171400
Create Date: 2026-08-20 10:00:00.000000

uq_fleet_alert_active: (rule_id, vehicle_id) WHERE status='ACTIVE' 的 partial
unique index —— DB 级兜底 service 层 _has_active_record 去重 (check-then-act
窗口下并发扫描同车同规则可双写 active 记录)。

WHERE 必须用枚举 *name* 大写 'ACTIVE' 而非小写 value: SAEnum 默认
values_callable=None, SQLite/PG 均存 name (卡 d9bba836 / 71e2f120 同款坑)。
vehicle_id 可 NULL, 多 NULL 不冲突, 索引天然不约束。

上线前收敛历史重复: 同 (rule_id, vehicle_id) 多条 ACTIVE 只留最新 (MAX(id)),
其余置 RESOLVED (alert_value 追加留痕)。幂等: 收敛零行命中 + 索引 inspector
判存 (SQLite 无 CREATE INDEX IF NOT EXISTS)。表不存在 (极端旧库) 整跳过。
可逆: downgrade 仅 DROP INDEX。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608201000"
down_revision: Union[str, Sequence[str], None] = "202608171400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "fleet_alert_records"
INDEX_NAME = "uq_fleet_alert_active"

# WHERE 用枚举 name 大写 (见模块 docstring)
_ACTIVE_WHERE = "status = 'ACTIVE'"

_CONVERGE_SQL = f"""
UPDATE {TABLE}
SET status = 'RESOLVED',
    alert_value = COALESCE(alert_value, '') || ' [迁移202608201000收敛:重复active仅留最新]'
WHERE {_ACTIVE_WHERE}
  AND vehicle_id IS NOT NULL
  AND id NOT IN (
      SELECT MAX(id) FROM {TABLE}
      WHERE {_ACTIVE_WHERE} AND vehicle_id IS NOT NULL
      GROUP BY rule_id, vehicle_id
  )
"""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return

    bind.execute(sa.text(_CONVERGE_SQL))

    existing = {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX_NAME not in existing:
        op.create_index(
            INDEX_NAME,
            TABLE,
            ["rule_id", "vehicle_id"],
            unique=True,
            postgresql_where=sa.text(_ACTIVE_WHERE),
            sqlite_where=sa.text(_ACTIVE_WHERE),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name=TABLE)
