"""revenue_daily / station_daily_metrics 幂等唯一约束 (卡 9863018d)

Revision ID: 202608301200
Revises: 202608301100
Create Date: 2026-08-30 12:00:00.000000

Celery 幂等审计发现的真缺口: build_revenue_daily / build_station_daily_metrics
是 check-then-act + db.add 且无 IntegrityError 兜底, 目标表也无唯一约束。
并发 worker (beat 重叠 / acks_late=True 重投递 / 手动补算) 会插重复行,
下游 revenue_stats 的 func.sum(paid_revenue) 直接双倍计算营收。

对齐卡 97c83af9 (daily_settlements) 范式:
1. revenue_daily.user_type 可 NULL, PG unique 视多个 NULL 为不同值不去重 →
   新增非 NULL 哨兵列 user_type_key = COALESCE(user_type, ''), 唯一约束建在
   (record_date, station_id, user_type_key) 上。station_id 虽建表 nullable,
   但 ChargingOrder.station_id NOT NULL 且 build 按其分组, 恒写非 NULL,
   无需哨兵。
2. station_daily_metrics 两列均 NOT NULL, 直接 (station_id, record_date)。
3. 建约束前先查重合并 (保每组 MIN(id) 删其余), inspector 判存跳过 (幂等)。
4. SQLite 建唯一索引用 create_index(unique=True) 而非 create_unique_constraint;
   downgrade 对称 drop, 哨兵列保留不丢数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608301200"
down_revision: Union[str, Sequence[str], None] = "202608301100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(i["name"] == name for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── revenue_daily: 补 user_type_key 哨兵列 + 唯一约束 ──
    if inspector.has_table("revenue_daily"):
        cols = {c["name"] for c in inspector.get_columns("revenue_daily")}
        if "user_type_key" not in cols:
            op.add_column(
                "revenue_daily",
                sa.Column("user_type_key", sa.String(50), nullable=False, server_default=""),
            )
        # 回填: NULL user_type → ''
        bind.execute(sa.text(
            "UPDATE revenue_daily SET user_type_key = COALESCE(user_type, '')"
        ))
        # 查重合并: 保留每组最小 id, 删其余 (避免建约束时撞重复数据)
        bind.execute(sa.text(
            "DELETE FROM revenue_daily WHERE id NOT IN ("
            "  SELECT MIN(id) FROM revenue_daily"
            "  GROUP BY record_date, station_id, user_type_key)"
        ))
        if not _has_index(inspector, "revenue_daily", "uq_rev_date_station_utype"):
            op.create_index(
                "uq_rev_date_station_utype", "revenue_daily",
                ["record_date", "station_id", "user_type_key"], unique=True,
            )

    # ── station_daily_metrics: 唯一约束 (两列均 NOT NULL, 无 NULL 坑) ──
    if inspector.has_table("station_daily_metrics"):
        bind.execute(sa.text(
            "DELETE FROM station_daily_metrics WHERE id NOT IN ("
            "  SELECT MIN(id) FROM station_daily_metrics"
            "  GROUP BY station_id, record_date)"
        ))
        if not _has_index(inspector, "station_daily_metrics", "uq_sdm_station_date"):
            op.create_index(
                "uq_sdm_station_date", "station_daily_metrics",
                ["station_id", "record_date"], unique=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, name in [
        ("station_daily_metrics", "uq_sdm_station_date"),
        ("revenue_daily", "uq_rev_date_station_utype"),
    ]:
        if inspector.has_table(table) and _has_index(inspector, table, name):
            op.drop_index(name, table_name=table)
    # user_type_key 列保留 (downgrade 只撤约束, 不丢数据)
