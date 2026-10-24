"""add_tenant_usage

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-07-25 20:00:00.000000

租户用量统计 (admin-platform-spec):
- tenant_usage: 每租户每日一条用量快照（站点/设备/用户数、存储、API 调用），
  供 GET /api/v1/tenants/{id}/usage 查询趋势。

幂等: 用 inspector 判表存在再建，兼容已 create_all 的环境。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'g4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, 'tenant_usage'):
        op.create_table(
            'tenant_usage',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('record_date', sa.Date(), nullable=False),
            sa.Column('station_count', sa.Integer(), nullable=True),
            sa.Column('device_count', sa.Integer(), nullable=True),
            sa.Column('user_count', sa.Integer(), nullable=True),
            sa.Column('storage_used_gb', sa.Float(), nullable=True),
            sa.Column('api_calls_today', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_tenant_usage_id', 'tenant_usage', ['id'])
        op.create_index(
            'idx_tenant_usage_tenant_date', 'tenant_usage',
            ['tenant_id', 'record_date'], unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, 'tenant_usage'):
        op.drop_index('idx_tenant_usage_tenant_date', table_name='tenant_usage')
        op.drop_index('ix_tenant_usage_id', table_name='tenant_usage')
        op.drop_table('tenant_usage')
