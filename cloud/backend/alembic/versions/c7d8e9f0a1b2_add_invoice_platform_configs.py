"""add_invoice_platform_configs

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23 22:45:00.000000

第三方开票平台配置表（团队级隔离: 百旺/航信/诺诺）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 invoice_platform_configs 表"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('invoice_platform_configs'):
        return  # Table already exists (created by baseline schema)

    op.create_table('invoice_platform_configs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('platform_type', sa.Enum('baiwang', 'hangxin', 'nuonuo', 'other', name='platformtype'), nullable=False),
        sa.Column('platform_name', sa.String(length=100), nullable=False),
        sa.Column('api_url', sa.String(length=500), nullable=True),
        sa.Column('app_key', sa.String(length=200), nullable=True),
        sa.Column('app_secret', sa.String(length=500), nullable=True),
        sa.Column('taxpayer_id', sa.String(length=50), nullable=True),
        sa.Column('tax_classification_code', sa.String(length=50), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_ipc_team', 'invoice_platform_configs', ['team_id'])
    op.create_index('idx_ipc_team_default', 'invoice_platform_configs', ['team_id', 'is_default'])
    op.create_index('idx_ipc_team_enabled', 'invoice_platform_configs', ['team_id', 'enabled'])


def downgrade() -> None:
    """删除 invoice_platform_configs 表"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('invoice_platform_configs'):
        op.drop_index('idx_ipc_team_enabled', table_name='invoice_platform_configs')
        op.drop_index('idx_ipc_team_default', table_name='invoice_platform_configs')
        op.drop_index('idx_ipc_team', table_name='invoice_platform_configs')
        op.drop_table('invoice_platform_configs')
    sa.Enum(name='platformtype').drop(bind, checkfirst=True)
