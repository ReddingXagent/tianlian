"""refund_records: 加 prev_payment_status + channel_refund_no (卡 aa88371f)

Revision ID: 202608070400
Revises: 202608070300
Create Date: 2026-08-07 04:00:00.000000

退款链路财务边界修复 (卡 aa88371f) 配套 schema:
- prev_payment_status: 退款发起前订单支付状态快照, reject 时恢复
  (修复缺陷2: reject 硬编码 REFUNDING→PAID; PARTIAL 退款被拒应恢复 PARTIAL)。
- channel_refund_no: 渠道(IM-B)退款单号, complete 调 wx_pay 退款后填 (缺陷5)。

两列均 nullable (历史数据无值; 模型层默认 nullable=True)。
PG 原生 ADD COLUMN; SQLite batch_alter_table 表重建, 两种 dialect 均安全,
对已 nullable 的列为 no-op, 幂等。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608070400"
down_revision: Union[str, Sequence[str], None] = "202608070300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """refund_records 新增 prev_payment_status + channel_refund_no 两列。"""
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此列 → 跳过; 生产库列不存在 → add。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("refund_records"):
        return
    existing_cols = {c['name'] for c in inspector.get_columns("refund_records")}
    with op.batch_alter_table("refund_records", schema=None) as batch_op:
        if "prev_payment_status" not in existing_cols:
            batch_op.add_column(
                sa.Column(
                    "prev_payment_status",
                    sa.String(length=32),
                    nullable=True,
                    comment="退款发起前订单支付状态快照(reject时恢复)",
                )
            )
        if "channel_refund_no" not in existing_cols:
            batch_op.add_column(
                sa.Column(
                    "channel_refund_no",
                    sa.String(length=64),
                    nullable=True,
                    comment="渠道退款单号(IM-B退款成功后填)",
                )
            )


def downgrade() -> None:
    """回滚: 移除两列 (数据无依赖, 安全)。"""
    with op.batch_alter_table("refund_records", schema=None) as batch_op:
        batch_op.drop_column("channel_refund_no")
        batch_op.drop_column("prev_payment_status")
