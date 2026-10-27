"""payment_orders: appid 硬闸列 (卡 7f5b4d4f A2)

Revision ID: 202608171400
Revises: 202608170900
Create Date: 2026-08-17 14:00:00.000000

IM-B支付真云化 A2: PaymentOrder 加 appid 列 (nullable), prepay 下单时按
scene 从 settings 写入, 回调 sp_appid 与之比对 (不一致拒绝落 PAID)。
存量行为 NULL → 回调跳过比对 + 日志留痕 (兼容期), 不破坏存量数据。

幂等: 列用 inspector 判存跳过, 重复执行不炸 (与 202608170900 同模式)。
SQLite 无 ADD COLUMN IF NOT EXISTS。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608171400"
down_revision: Union[str, Sequence[str], None] = "202608170900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "payment_orders"):
        # 极端旧库 (表由 create_all/更早迁移建): 判表保护, 不炸迁移链
        return

    if not _has_column(bind, "payment_orders", "appid"):
        op.add_column(
            "payment_orders",
            sa.Column("appid", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "payment_orders"):
        return

    if _has_column(bind, "payment_orders", "appid"):
        op.drop_column("payment_orders", "appid")
