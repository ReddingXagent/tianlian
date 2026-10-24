"""carbon_reduction_records 幂等唯一约束 (卡 7ea84b57)

Revision ID: 202608301300
Revises: 202608301200
Create Date: 2026-08-30 13:00:00.000000

aggregate_carbon_for_date 注释自称幂等 (vehicle_id+record_date), 实际是
check-then-act + db.add 且无 IntegrityError 兜底, 表上 idx_crr_vehicle_date
是普通索引。celery worker_concurrency=4 + task_acks_late=True 下, beat 重叠/
重投递/手动补算会插重复行, 下游 carbon_emission / enterprise_vehicles 的
func.sum 碳减排量/等效节油量直接双倍计算。

对齐卡 97c83af9 / 9863018d 范式:
1. vehicle_id / record_date 均非 NULL, 直接建 (vehicle_id, record_date) 唯一
   约束, 无需哨兵列。
2. 建约束前先查重合并 (保每组 MIN(id) 删其余; 重复行为聚合值, MIN id 行即可)。
3. SQLite 建唯一索引用 create_index(unique=True); 表级 UniqueConstraint 生成
   匿名 autoindex, inspector.get_indexes 不可见, 判存在性须走 PRAGMA index_list
   看 origin='u' (卡 9863018d 教训)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608301300"
down_revision: Union[str, Sequence[str], None] = "202608301200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "carbon_reduction_records"
INDEX_NAME = "uq_crr_vehicle_date"


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(i["name"] == name for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE):
        return

    # 查重合并: 保留每组最小 id, 删其余 (重复行是聚合值, MIN id 行为准)
    bind.execute(sa.text(
        f"DELETE FROM {TABLE} WHERE id NOT IN ("
        f"  SELECT MIN(id) FROM {TABLE} GROUP BY vehicle_id, record_date)"
    ))
    if not _has_index(inspector, TABLE, INDEX_NAME):
        op.create_index(
            INDEX_NAME, TABLE, ["vehicle_id", "record_date"], unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE) and _has_index(inspector, TABLE, INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE)
