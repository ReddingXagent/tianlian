"""work_orders.creator_id nullable: 系统自动创建工单无真实创建人

Revision ID: b1c2d3e4f5a6
Revises: f5a6b7c8d9e0
Create Date: 2026-07-28 20:10:00.000000

卡片 1236b769: 生产 POST /api/v1/work-orders 500 IntegrityError
ForeignKeyViolation work_orders_creator_id_fkey。
根因有二:
1) workorders.py 创建端点曾硬编码 creator_id=999 (不在 users) → FK 违约 500;
2) alarm_rule_service._maybe_create_workorder 曾硬编码 creator_id=0 (不在 users)
   → FK 违约被 except 吞掉, 自动工单静默从未创建。

修复后自动工单 creator_id=None (无真实创建人), 需保证列允许 NULL。
模型层 Column 默认 nullable=True, baseline create_all 即为 nullable;
本迁移为防御性显式声明 (防历史迁移误改 NOT NULL), 并对齐模型意图。
PG 上 ALTER COLUMN ... DROP NOT NULL 对已 nullable 列为 no-op, 幂等。

downgrade 保留 nullable=True: 系统工单 creator_id 已为 NULL, 强制 SET NOT NULL
会失败; 列语义本就可空, 回滚不收紧约束即可安全执行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """creator_id 允许 NULL (系统自动创建工单无真实创建人)。

    batch_alter_table: PG 退化为原生 ALTER COLUMN; SQLite 用表重建,
    两种 dialect 均安全。对已 nullable 的列为 no-op, 幂等。
    """
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "creator_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    """保留 nullable=True (见模块 docstring: 已有 NULL 数据, 不可收紧 NOT NULL)。"""
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "creator_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
