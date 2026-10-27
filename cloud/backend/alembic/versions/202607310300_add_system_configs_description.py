"""system_configs: 补 description 列 + id/config_key 索引 (对齐 SystemConfig model)

Revision ID: 202607310300
Revises: 202607310200
Create Date: 2026-07-31 03:00:00.000000

D8 漂移修复: 石猴补 SystemConfig ORM model (app/models/system_config.py) 时未附带
system_configs 建表迁移, 生产该表为早期 create_all 残留 (缺 description 列 + 2 索引),
部署 schema 漂移检测报 "缺列 1 / 缺索引 2"。本迁移把迁移链与 model 对齐 [D8-drift-fix]。

幂等设计:
- 全新库 (仅走迁移, 无 system_configs): 建完整表 + 索引。
- 存量库 (生产, 表已存在但缺 description/索引): 仅补缺失的列与索引。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '202607310300'
down_revision = '202607310200'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, index: str) -> bool:
    return any(i["name"] == index for i in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _has_table('system_configs'):
        # 全新库: 建完整表 (列名与 model 对齐, config_type 映射 DB 列 ``type``)
        op.create_table(
            'system_configs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('config_key', sa.String(length=100), nullable=False),
            sa.Column('config_value', sa.JSON(), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('type', sa.String(length=50), nullable=False, server_default='global'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(op.f('ix_system_configs_id'), 'system_configs', ['id'], unique=False)
        op.create_index(op.f('ix_system_configs_config_key'), 'system_configs', ['config_key'], unique=True)
        return

    # 存量库: 仅补缺失部分
    if not _has_column('system_configs', 'description'):
        op.add_column('system_configs', sa.Column('description', sa.String(length=255), nullable=True))
    if not _has_index('system_configs', 'ix_system_configs_id'):
        op.create_index(op.f('ix_system_configs_id'), 'system_configs', ['id'], unique=False)
    if not _has_index('system_configs', 'ix_system_configs_config_key'):
        op.create_index(op.f('ix_system_configs_config_key'), 'system_configs', ['config_key'], unique=True)


def downgrade() -> None:
    if not _has_table('system_configs'):
        return
    if _has_index('system_configs', 'ix_system_configs_config_key'):
        op.drop_index(op.f('ix_system_configs_config_key'), table_name='system_configs')
    if _has_index('system_configs', 'ix_system_configs_id'):
        op.drop_index(op.f('ix_system_configs_id'), table_name='system_configs')
    if _has_column('system_configs', 'description'):
        op.drop_column('system_configs', 'description')
