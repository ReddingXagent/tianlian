"""add_station_tenant_id

Revision ID: j7e8f9a0b1c2
Revises: i6d7e8f9a0b1
Create Date: 2026-07-25 12:00:00.000000

多租户隔离: 给 stations 表补 tenant_id 列。

背景: 模型层 (app/models/station.py) 已为 Station 启用 tenant_id 字段
(Integer, ForeignKey("tenants.id"), nullable=True, index=True), 但持久库
(开发 SQLite / 生产 Postgres) 的 stations 表仍缺该列。租户详情统计端点
/api/v1/tenants/{id}/stats 按 Station.tenant_id 过滤会抛
"no such column: stations.tenant_id", 导致 test_tenant_stats_detail 等用例失败。

本 migration 幂等地补齐该列(已有则跳过), 保证 schema 与模型一致。
向后兼容: nullable=True 且无 server_default —— 既有站点归为 NULL(平台共享/未分配),
不破坏生产已有数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j7e8f9a0b1c2"
down_revision: Union[str, None] = "i6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "stations"
_COLUMN = "tenant_id"
_INDEX = "ix_stations_tenant_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_TABLE):
        # 表尚未创建(create_all 会按最新模型建, 已含 tenant_id) -> 无需补列
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Integer(), nullable=True,
                      comment="所属租户(多租户隔离); NULL=平台共享/未分配"),
        )

    # 幂等建索引
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX not in existing_indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_TABLE):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX in existing_indexes:
        op.drop_index(_INDEX, table_name=_TABLE)

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_cols:
        op.drop_column(_TABLE, _COLUMN)
