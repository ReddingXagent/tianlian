"""add protocol instances & parser configs tables

Revision ID: 202606020200
Revises: 202605260215
Create Date: 2026-06-02 20:06:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '202606020200'
down_revision = '202605260215'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建协议实例表
    op.create_table('protocol_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('protocol_type', sa.String(length=50), nullable=False, comment='协议类型: modbus_rtu, mqtt, rest'),
        sa.Column('gateway_id', sa.Integer(), nullable=True, comment='关联网关ID'),
        sa.Column('device_type', sa.String(length=100), nullable=True, comment='设备类型标识'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='协议特定配置'),
        sa.Column('parser_schema', sa.String(length=100), nullable=True, comment='使用的解析Schema'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='stopped', comment='实例状态: running, stopped, error'),
        sa.Column('connection_status', sa.String(length=20), nullable=False, server_default='disconnected', comment='连接状态: connected, disconnected, connecting'),
        sa.Column('last_connected', sa.DateTime(), nullable=True, comment='最后连接时间'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_protocol_instances_protocol_type'), 'protocol_instances', ['protocol_type'], unique=False)
    op.create_index(op.f('ix_protocol_instances_status'), 'protocol_instances', ['status'], unique=False)
    op.create_index(op.f('ix_protocol_instances_gateway_id'), 'protocol_instances', ['gateway_id'], unique=False)

    # 创建解析器配置表
    op.create_table('parser_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('device_type', sa.String(length=100), nullable=False, comment='设备类型标识'),
        sa.Column('protocol', sa.String(length=50), nullable=False, comment='协议类型'),
        sa.Column('parser_schema', sa.String(length=100), nullable=True, comment='使用的解析Schema'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='解析器配置参数'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active', comment='配置状态: active, inactive'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_parser_configs_device_type'), 'parser_configs', ['device_type'], unique=False)
    op.create_index(op.f('ix_parser_configs_protocol'), 'parser_configs', ['protocol'], unique=False)
    op.create_index(op.f('ix_parser_configs_status'), 'parser_configs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_parser_configs_status'), table_name='parser_configs')
    op.drop_index(op.f('ix_parser_configs_protocol'), table_name='parser_configs')
    op.drop_index(op.f('ix_parser_configs_device_type'), table_name='parser_configs')
    op.drop_table('parser_configs')

    op.drop_index(op.f('ix_protocol_instances_gateway_id'), table_name='protocol_instances')
    op.drop_index(op.f('ix_protocol_instances_status'), table_name='protocol_instances')
    op.drop_index(op.f('ix_protocol_instances_protocol_type'), table_name='protocol_instances')
    op.drop_table('protocol_instances')