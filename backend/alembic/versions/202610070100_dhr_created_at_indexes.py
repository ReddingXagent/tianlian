"""device_health_records created_at 索引 (card 8b9f543a)

Revision ID: 202610070100
Revises: 202610051300
Create Date: 2026-10-07 01:00:00.000000

device_health_records.created_at 零索引修复 (卡 8b9f543a-0880-485f-b1f5-2a9a4dd5ff79):
纯索引增量, 不动查询逻辑。新增两条索引:
  - ix_dhr_device_created (device_id, created_at):
    diagnosis.py 时间窗查询 (device_id + created_at>=N天) 及
    services/health.py group_by(device_id).max(created_at) join 回查
  - ix_dhr_created_at (created_at):
    health_monitor.py 健康总览全局 ORDER BY created_at DESC LIMIT 20

幂等守卫 (参照 0c60e5c087e0 has_table 模式):
表不存在(单表隔离库/全新库) -> up/down 双向早退; 索引已存在 -> 跳过。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610070100"
down_revision: Union[str, None] = "202610051300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "device_health_records"
_INDEXES = [
    ("ix_dhr_device_created", ["device_id", "created_at"]),
    ("ix_dhr_created_at", ["created_at"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    for name, cols in _INDEXES:
        if name in existing:
            continue
        op.create_index(name, _TABLE, cols, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    for name, _ in _INDEXES:
        if name not in existing:
            continue
        op.drop_index(name, table_name=_TABLE)
