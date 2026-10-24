"""device_upgrade_tasks 设备级固件升级任务表 (卡 43b26421)

前端 deviceAPI.firmware 三端点 (GET/POST /devices/{id}/firmware*) 此前后端
零实现, UI 点击「固件」即 404。本迁移补设备维度 OTA 任务表:
- device_id FK devices.id, index
- target_version / url / force(0|1)
- status 默认 pending, progress 默认 0, error_message
- created_by / created_at / updated_at

与网关级 upgrade_tasks (gateway_id 维度, gateways.py 语义被既有测试锁死) 正交,
不改动其模型。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608301100"
down_revision: Union[str, Sequence[str], None] = "202608301000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "device_upgrade_tasks"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("target_version", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("force", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_device_upgrade_tasks_id"), _TABLE, ["id"])
    op.create_index(op.f("ix_device_upgrade_tasks_device_id"), _TABLE, ["device_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_device_upgrade_tasks_device_id"), table_name=_TABLE)
    op.drop_index(op.f("ix_device_upgrade_tasks_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
