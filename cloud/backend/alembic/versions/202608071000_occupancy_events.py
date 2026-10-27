"""occupancy_events: 无人值守占位费事件表 (工作卡 f0db2036)

Revision ID: 202608071000
Revises: 202608070900
Create Date: 2026-08-07 10:00:00.000000

占位费自动化: 记录车牌识别系统上报的车位占用事件(车牌+起止时间),
联动占位费计费(复用 billing_engine.compute_parking_fee_full):
- 有充电订单 → 占位费并入订单账单
- 纯占位     → event 自身承载独立账单(fee_status=BILLED)

幂等键: (plate_number, station_id, exit_at) — 同站同车牌未离场(exit_at IS NULL)
的事件唯一, 供 service 层"未离场更新"查询(多 NULL 不冲突, 与 charging_orders
transaction_id 幂等同模式)。

枚举: occupancyeventsource(alpr/charging_estimate), occupancyfeestatus
(pending/billed/merged/exempt)。

幂等建表: inspector 判表存在再建, 兼容已 create_all 的测试环境
(与 invoice_requests / cf614348 / c7523ad8 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608071000"
down_revision: Union[str, Sequence[str], None] = "202608070900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 枚举字面值 (与 app.models.parking_event 一致)
_SOURCE_VALUES = ("alpr", "charging_estimate")
_FEE_STATUS_VALUES = ("pending", "billed", "merged", "exempt")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "occupancy_events"):
        op.create_table(
            "occupancy_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("plate_number", sa.String(length=20), nullable=False, comment="车牌号"),
            sa.Column(
                "station_id", sa.Integer(),
                sa.ForeignKey("stations.id"), nullable=False, comment="站点ID"),
            sa.Column("enter_at", sa.DateTime(timezone=True), nullable=False, comment="进场时间(UTC)"),
            sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True, comment="离场时间(UTC), NULL=未离场"),
            sa.Column(
                "source",
                sa.Enum(*_SOURCE_VALUES, name="occupancyeventsource"),
                nullable=False, server_default="alpr",
                comment="来源: alpr/charging_estimate"),
            sa.Column(
                "match_order_id", sa.Integer(),
                sa.ForeignKey("charging_orders.id"), nullable=True,
                comment="匹配的充电订单ID"),
            sa.Column("occupancy_minutes", sa.Integer(), nullable=True, comment="占位时长(分钟)"),
            sa.Column(
                "fee_status",
                sa.Enum(*_FEE_STATUS_VALUES, name="occupancyfeestatus"),
                nullable=False, server_default="pending",
                comment="占位费状态: pending/billed/merged/exempt"),
            sa.Column(
                "fee_amount", sa.Numeric(12, 2),
                nullable=True, comment="占位费(元)"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("idx_occevt_plate_station_exit", "occupancy_events",
                        ["plate_number", "station_id", "exit_at"])
        op.create_index("idx_occevt_station", "occupancy_events", ["station_id"])
        op.create_index("idx_occevt_status", "occupancy_events", ["fee_status"])
        op.create_index("idx_occevt_order", "occupancy_events", ["match_order_id"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, "occupancy_events"):
        for idx in (
            "idx_occevt_order",
            "idx_occevt_status",
            "idx_occevt_station",
            "idx_occevt_plate_station_exit",
        ):
            try:
                op.drop_index(idx, table_name="occupancy_events")
            except Exception:
                pass
        op.drop_table("occupancy_events")
        # SQLite 不持久化 enum type 且无 DROP TYPE 语法(会抛 syntax error) → 容错跳过;
        # PG 下正常清理 enum type。包 try/except 保证两种 dialect downgrade 都完整执行
        # (否则 DROP TYPE 抛错会中断 downgrade, alembic_version 不回退 → 状态不一致)。
        for t in ("occupancyfeestatus", "occupancyeventsource"):
            try:
                bind.execute(sa.text(f"DROP TYPE IF EXISTS {t}"))
            except Exception:
                pass
