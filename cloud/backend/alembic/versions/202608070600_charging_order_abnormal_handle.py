"""charging_orders: 异常订单处理闭环字段 (卡 f730f63c)

Revision ID: 202608070600
Revises: 202608070500
Create Date: 2026-08-07 06:00:00.000000

ChargingOrder 新增 4 列 (均 nullable), 支撑异常订单(failed/cancelled)操作闭环:
- abnormal_handle_type     处理类型: refunded/written_off/false_alarm
- abnormal_handle_remark   处理备注
- abnormal_handled_at      处理时间(UTC)
- abnormal_handled_by      处理人ID

全列 nullable, 历史订单无值; abnormal_handle_type 非空即视为"已处理"
(供 /operate/orders 列表与前端 AbnormalOrders 操作列显隐判定)。
PG 原生 ADD COLUMN; SQLite batch_alter_table 表重建, 两种 dialect 均安全。
_has_column 守卫保证幂等, 与 create_all 基线共存不冲突 (测试库走 create_all 不经此迁移)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608070600"
down_revision: Union[str, Sequence[str], None] = "202608070500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = [
    ("abnormal_handle_type", sa.String(length=32)),
    ("abnormal_handle_remark", sa.String(length=500)),
    ("abnormal_handled_at", sa.DateTime()),
    ("abnormal_handled_by", sa.Integer()),
]


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("charging_orders"):
        # 表缺失(单表隔离库) -> 优雅跳过
        return
    for name, coltype in _NEW_COLUMNS:
        if not _has_column(bind, "charging_orders", name):
            with op.batch_alter_table("charging_orders") as batch_op:
                batch_op.add_column(sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("charging_orders"):
        # 表缺失 -> 无列可删, 优雅跳过
        return
    for name, _ in reversed(_NEW_COLUMNS):
        if _has_column(bind, "charging_orders", name):
            with op.batch_alter_table("charging_orders") as batch_op:
                batch_op.drop_column(name)
