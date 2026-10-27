"""invoice_requests: 红冲 void 标记列 (Phase2-B2, 卡 f42bdf5a)

Revision ID: 202608170900
Revises: 202608161500
Create Date: 2026-08-17 09:00:00.000000

R1 方案b (丁哥拍板): status 三态 pending/issued/rejected 不变, 红冲 =
ISSUED 发票上打 voided 标记。契约只增不破 —— 响应新增可选字段非破坏性变更。

新列: voided(Boolean default 0) / void_reason(String 500) /
voided_by(Integer) / voided_at(DateTime)。

幂等: 表不存在 (极端旧库) 整跳过; 列用 inspector 判存跳过, 重复执行不炸
(与 202608070900 / cf614348 同模式)。SQLite 无 ADD COLUMN IF NOT EXISTS。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608170900"
down_revision: Union[str, Sequence[str], None] = "202608161500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


# (列名, 定义) —— 顺序即加列顺序, 无依赖关系
_VOID_COLUMNS = [
    ("voided", lambda: sa.Column(
        "voided", sa.Boolean(), nullable=False, server_default=sa.false(),
    )),
    ("void_reason", lambda: sa.Column(
        "void_reason", sa.String(length=500), nullable=True,
    )),
    ("voided_by", lambda: sa.Column("voided_by", sa.Integer(), nullable=True)),
    ("voided_at", lambda: sa.Column(
        "voided_at", sa.DateTime(timezone=True), nullable=True,
    )),
]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "invoice_requests"):
        # 极端旧库 (表由 202608070900 建): alembic 链会先跑该迁移再到此, 正常不可达
        return

    for name, make in _VOID_COLUMNS:
        if _has_column(bind, "invoice_requests", name):
            continue  # 已存在 (重复执行 / create_all 已建) → 跳过
        op.add_column("invoice_requests", make())


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "invoice_requests"):
        return

    for name in reversed([n for n, _ in _VOID_COLUMNS]):
        if not _has_column(bind, "invoice_requests", name):
            continue
        op.drop_column("invoice_requests", name)
