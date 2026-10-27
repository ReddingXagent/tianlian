"""analytics_results 幂等唯一约束 (卡 77184280)

Revision ID: 202610131000
Revises: 202610111000
Create Date: 2026-10-13 10:00:00.000000

Celery 幂等审计 (0220轮) 发现的缺口: calculate_health_score_task /
analyze_efficiency_task 每次运行/重试直接 INSERT 新行, 重试即表膨胀;
读侧只按 generated_at 取 latest, 单行覆盖 upsert 不破坏语义。

对齐卡 9863018d (revenue_daily) 范式:
1. 唯一约束 (device_id, analysis_type) 建为同名字唯一索引 uq_ar_device_type
   (SQLite 建约束须用 create_index(unique=True))。
2. 两列写入方均恒写非 NULL (device_id NOT NULL, analysis_type 恒为
   'health_score'/'efficiency'), 无 PG unique 多 NULL 不去重坑, 无需哨兵列。
3. 建约束前查重合并 (保每组 MIN(id) 删其余), inspector 判存跳过 (幂等)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610131000"
down_revision: Union[str, Sequence[str], None] = "202610111000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(i["name"] == name for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("analytics_results"):
        # 查重合并: 保留每组 (device_id, analysis_type) 最小 id, 删其余
        bind.execute(sa.text(
            "DELETE FROM analytics_results WHERE id NOT IN ("
            "  SELECT MIN(id) FROM analytics_results"
            "  GROUP BY device_id, analysis_type)"
        ))
        if not _has_index(inspector, "analytics_results", "uq_ar_device_type"):
            op.create_index(
                "uq_ar_device_type", "analytics_results",
                ["device_id", "analysis_type"], unique=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("analytics_results") and _has_index(
        inspector, "analytics_results", "uq_ar_device_type"
    ):
        op.drop_index("uq_ar_device_type", table_name="analytics_results")
