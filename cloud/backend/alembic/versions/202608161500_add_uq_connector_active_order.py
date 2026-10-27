"""uq_connector_active_order partial unique index 落地 (卡 71e2f120)

Revision ID: 202608161500
Revises: 202608161400
Create Date: 2026-08-16 15:00:00.000000

模型 app/models/charging_order.py:120 早已声明该索引, 但迁移链从未落地 →
生产 PG 同枪并发建单防线 (卡 d9bba836 的 DB 级兜底) 实际未生效。开发 SQLite
由 create_all 建索引故无感, 生产 PG 旧库缺索引。本迁移补齐并先收敛历史重复。

两步:
1. 收敛历史重复: 同 (device_id, connector_id) 多条 PENDING/CHARGING 订单只保留
   最新一条 (MAX(id)), 其余置 order_status=CANCELLED 并写固定 remark 追溯。
   终态订单与 connector_id IS NULL 的行不参与 (SQL 多 NULL 不冲突, 索引亦不约束)。
2. CREATE UNIQUE INDEX uq_connector_active_order ON charging_orders
   (device_id, connector_id) WHERE order_status IN ('PENDING', 'CHARGING')。

WHERE 必须用枚举 *name* 大写 'PENDING'/'CHARGING' 而非小写 value: SAEnum 默认
values_callable=None, SQLite/PG 均存 name; 用 value 会导致 WHERE 永不命中、
索引形同虚设 (模型注释明示, 实测验证, 卡 d9bba836)。

收敛 SQL 用纯子查询 (UPDATE ... WHERE id NOT IN (SELECT MAX(id) ...)), 不用
UPDATE...FROM — 后者是 PG 方言, SQLite 不支持; 子查询双方言可移植。

幂等守卫: 索引用 inspector 判存 (SQLite 无 CREATE INDEX IF NOT EXISTS, 见
9a3c7e1f4d82 同款机制); 收敛 UPDATE 天然幂等 (重复跑零行命中)。表不存在
(极端旧库) 则整跳过。

可逆: downgrade 仅 DROP INDEX, 不恢复被收敛的订单 (数据收敛不可逆, 留痕在
remark); 判存守卫。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608161500"
down_revision: Union[str, Sequence[str], None] = "202608161400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_connector_active_order"
TABLE = "charging_orders"
REMARK = "迁移71e2f120收敛：partial unique index上线前清理重复active订单"

# WHERE 用枚举 name 大写 (见模块 docstring); 与模型 __table_args__ 的
# postgresql_where/sqlite_where 保持一字不差。
_ACTIVE_WHERE = "order_status IN ('PENDING', 'CHARGING')"

# 收敛历史重复: 每组 (device_id, connector_id) 的 active 订单只留 MAX(id)。
# connector_id IS NULL 的行排除 (多 NULL 不冲突, 索引不约束, 不该动它们)。
_CONVERGE_SQL = f"""
UPDATE {TABLE}
SET order_status = 'CANCELLED',
    remark = '{REMARK}'
WHERE {_ACTIVE_WHERE}
  AND connector_id IS NOT NULL
  AND id NOT IN (
      SELECT MAX(id) FROM {TABLE}
      WHERE {_ACTIVE_WHERE} AND connector_id IS NOT NULL
      GROUP BY device_id, connector_id
  )
"""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return

    # 1) 收敛历史重复 active 订单 (幂等: 二次运行零行命中)
    bind.execute(sa.text(_CONVERGE_SQL))

    # 2) 建索引 (inspector 判存守卫, SQLite 无 IF NOT EXISTS)
    existing = {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX_NAME not in existing:
        op.create_index(
            INDEX_NAME,
            TABLE,
            ["device_id", "connector_id"],
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
