"""settlement/energy dispatch 幂等唯一约束 (卡 97c83af9)

Revision ID: 202608301000
Revises: 202608271500
Create Date: 2026-08-30 10:00:00.000000

celery 定时任务落库幂等此前纯靠应用层 check-then-act, worker_concurrency=4
并发 (beat 重叠 / acks_late=True worker lost 重投递 / 手动重跑) 会插重复行:
- daily_settlements:        同 (settlement_date, station_id) 重复
- payment_reconciliation:   同 (settlement_date, payment_channel) 重复
- energy_dispatch_plan:     同 (station_id, window_start) 重复 → 能量流水翻倍

本迁移补三张表的唯一约束。PG 坑规避:
1. daily_settlements.station_id 可 NULL (全平台汇总行), PG unique 视多个 NULL
   为不同值不去重 → 新增非 NULL 哨兵列 station_key = COALESCE(station_id, 0),
   唯一约束建在 (settlement_date, station_key) 上, 模型层 before_insert 事件
   保持同步。选哨兵键而非 NULLS NOT DISTINCT: 兼容 SQLite/低版本 PG, 且
   SQLite (开发库) 完全不支持 NULLS NOT DISTINCT。
2. 建约束前先查重合并 (保最小 id 行, 其余删除), 否则生产已有重复数据导致
   upgrade 失败。
3. 索引命名冲突: 本迁移只建唯一约束 (带唯一 name), 不 rename 既有普通索引。
   SQLite 建唯一索引用 create_index(unique=True) 而非 CREATE UNIQUE CONSTRAINT
   (ALTER ADD CONSTRAINT 不支持); op.create_unique_constraint 在 SQLite 会走
   batch 模式重建表, create_index(unique=True) 更直接且两方言通用。
   幂等: inspector 判存跳过; downgrade 对称 drop。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608301000"
down_revision: Union[str, Sequence[str], None] = "202608271500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(i["name"] == name for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── daily_settlements: 补 station_key 哨兵列 + 唯一约束 ──
    if inspector.has_table("daily_settlements"):
        cols = {c["name"] for c in inspector.get_columns("daily_settlements")}
        if "station_key" not in cols:
            op.add_column(
                "daily_settlements",
                sa.Column("station_key", sa.Integer(), nullable=False, server_default="0"),
            )
        # 回填: NULL=全平台 → 0
        bind.execute(sa.text(
            "UPDATE daily_settlements SET station_key = COALESCE(station_id, 0)"
        ))
        # 查重合并: 保留每组最小 id, 删其余 (避免建约束时撞重复数据)
        bind.execute(sa.text(
            "DELETE FROM daily_settlements WHERE id NOT IN ("
            "  SELECT MIN(id) FROM daily_settlements"
            "  GROUP BY settlement_date, station_key)"
        ))
        if not _has_index(inspector, "daily_settlements", "uq_ds_date_station"):
            op.create_index(
                "uq_ds_date_station", "daily_settlements",
                ["settlement_date", "station_key"], unique=True,
            )

    # ── payment_reconciliation: 唯一约束 (两列均 NOT NULL, 无 NULL 坑) ──
    if inspector.has_table("payment_reconciliation"):
        bind.execute(sa.text(
            "DELETE FROM payment_reconciliation WHERE id NOT IN ("
            "  SELECT MIN(id) FROM payment_reconciliation"
            "  GROUP BY settlement_date, payment_channel)"
        ))
        if not _has_index(inspector, "payment_reconciliation", "uq_pr_date_channel"):
            op.create_index(
                "uq_pr_date_channel", "payment_reconciliation",
                ["settlement_date", "payment_channel"], unique=True,
            )

    # ── energy_dispatch_plan: 同窗口唯一 (station_id NULL 行不受约束影响) ──
    if inspector.has_table("energy_dispatch_plan"):
        bind.execute(sa.text(
            "DELETE FROM energy_dispatch_plan WHERE id NOT IN ("
            "  SELECT MIN(id) FROM energy_dispatch_plan"
            "  GROUP BY station_id, window_start)"
        ))
        if not _has_index(inspector, "energy_dispatch_plan", "uq_edp_station_window"):
            op.create_index(
                "uq_edp_station_window", "energy_dispatch_plan",
                ["station_id", "window_start"], unique=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, name in [
        ("energy_dispatch_plan", "uq_edp_station_window"),
        ("payment_reconciliation", "uq_pr_date_channel"),
        ("daily_settlements", "uq_ds_date_station"),
    ]:
        if inspector.has_table(table) and _has_index(inspector, table, name):
            op.drop_index(name, table_name=table)
    # station_key 列保留 (downgrade 只撤约束, 不丢数据)
