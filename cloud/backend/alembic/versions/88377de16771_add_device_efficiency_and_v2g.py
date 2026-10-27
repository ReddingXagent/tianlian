"""add_device_efficiency_and_v2g

Revision ID: 88377de16771
Revises: 0001_baseline0001_baseline
Create Date: 2026-07-06 21:21:16.406337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88377de16771'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # === 设备效率日志表 ===
    if not inspector.has_table('device_efficiency_logs'):
        op.create_table('device_efficiency_logs',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('device_id', sa.BigInteger(), nullable=False),
            sa.Column('station_id', sa.BigInteger(), nullable=True),
            sa.Column('utilization', sa.Float(), nullable=True, comment='设备利用率(%)'),
            sa.Column('charge_efficiency', sa.Float(), nullable=True, comment='充电效率(%)'),
            sa.Column('generation_efficiency', sa.Float(), nullable=True, comment='发电效率(%)'),
            sa.Column('pv_pr', sa.Float(), nullable=True, comment='光伏PR性能比'),
            sa.Column('raw_data', sa.JSON(), nullable=True, comment='原始遥测数据快照'),
            sa.Column('metric_type', sa.String(length=50), nullable=True, comment='指标类型: utilization/charge/generation'),
            sa.Column('metric_name', sa.String(length=100), nullable=True, comment='指标名称'),
            sa.Column('metric_value', sa.Float(), nullable=True, comment='指标值'),
            sa.Column('unit', sa.String(length=20), nullable=True, comment='单位'),
            sa.Column('threshold_warn', sa.Float(), nullable=True, comment='告警阈值'),
            sa.Column('threshold_critical', sa.Float(), nullable=True, comment='严重阈值'),
            sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True, comment='记录时间'),
            sa.Column('log_date', sa.String(length=10), nullable=False, comment='日志日期 YYYY-MM-DD'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
            sa.ForeignKeyConstraint(['station_id'], ['stations.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_device_efficiency_logs_device_id'), 'device_efficiency_logs', ['device_id'], unique=False)
        op.create_index(op.f('ix_device_efficiency_logs_id'), 'device_efficiency_logs', ['id'], unique=False)
        op.create_index(op.f('ix_device_efficiency_logs_log_date'), 'device_efficiency_logs', ['log_date'], unique=False)
        op.create_index(op.f('ix_device_efficiency_logs_metric_type'), 'device_efficiency_logs', ['metric_type'], unique=False)
        op.create_index(op.f('ix_device_efficiency_logs_recorded_at'), 'device_efficiency_logs', ['recorded_at'], unique=False)
        op.create_index(op.f('ix_device_efficiency_logs_station_id'), 'device_efficiency_logs', ['station_id'], unique=False)

    # === V2G调度日志表 ===
    if not inspector.has_table('v2g_dispatch_logs'):
        op.create_table('v2g_dispatch_logs',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('device_id', sa.BigInteger(), nullable=False),
            sa.Column('dispatch_type', sa.String(length=20), nullable=False, comment='调度类型: charge/discharge/standby'),
            sa.Column('target_power_kw', sa.Float(), nullable=False, comment='目标功率(kW)'),
            sa.Column('actual_power_kw', sa.Float(), nullable=False, comment='实际功率(kW)'),
            sa.Column('status', sa.String(length=20), nullable=False, comment='状态: pending/executing/completed/failed'),
            sa.Column('start_at', sa.DateTime(timezone=True), nullable=True, comment='开始时间'),
            sa.Column('end_at', sa.DateTime(timezone=True), nullable=True, comment='结束时间'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
            sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_v2g_dispatch_logs_device_id'), 'v2g_dispatch_logs', ['device_id'], unique=False)
        op.create_index(op.f('ix_v2g_dispatch_logs_dispatch_type'), 'v2g_dispatch_logs', ['dispatch_type'], unique=False)
        op.create_index(op.f('ix_v2g_dispatch_logs_id'), 'v2g_dispatch_logs', ['id'], unique=False)
        op.create_index(op.f('ix_v2g_dispatch_logs_status'), 'v2g_dispatch_logs', ['status'], unique=False)

    # === Device表新增字段 (仅当 devices 表已存在且列不存在时) ===
    if inspector.has_table('devices'):
        existing_cols = {c['name'] for c in inspector.get_columns('devices')}
        if 'utilization_rate' not in existing_cols:
            op.add_column('devices', sa.Column('utilization_rate', sa.Float(), nullable=True, comment='设备利用率(%)'))
        if 'pv_pr_ratio' not in existing_cols:
            op.add_column('devices', sa.Column('pv_pr_ratio', sa.Float(), nullable=True, comment='光伏PR性能比'))
        if 'rated_power_kw' not in existing_cols:
            op.add_column('devices', sa.Column('rated_power_kw', sa.Float(), nullable=True, comment='额定功率(kW)'))
        if 'last_runtime_hours' not in existing_cols:
            op.add_column('devices', sa.Column('last_runtime_hours', sa.Float(), nullable=True, comment='最后运行时长(h)'))
        if 'total_runtime_hours' not in existing_cols:
            op.add_column('devices', sa.Column('total_runtime_hours', sa.Float(), nullable=True, comment='累计运行时长(h)'))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('devices'):
        existing_cols = {c['name'] for c in inspector.get_columns('devices')}
        if 'total_runtime_hours' in existing_cols:
            op.drop_column('devices', 'total_runtime_hours')
        if 'last_runtime_hours' in existing_cols:
            op.drop_column('devices', 'last_runtime_hours')
        if 'rated_power_kw' in existing_cols:
            op.drop_column('devices', 'rated_power_kw')
        if 'pv_pr_ratio' in existing_cols:
            op.drop_column('devices', 'pv_pr_ratio')
        if 'utilization_rate' in existing_cols:
            op.drop_column('devices', 'utilization_rate')

    if inspector.has_table('v2g_dispatch_logs'):
        op.drop_index(op.f('ix_v2g_dispatch_logs_status'), table_name='v2g_dispatch_logs')
        op.drop_index(op.f('ix_v2g_dispatch_logs_id'), table_name='v2g_dispatch_logs')
        op.drop_index(op.f('ix_v2g_dispatch_logs_dispatch_type'), table_name='v2g_dispatch_logs')
        op.drop_index(op.f('ix_v2g_dispatch_logs_device_id'), table_name='v2g_dispatch_logs')
        op.drop_table('v2g_dispatch_logs')

    if inspector.has_table('device_efficiency_logs'):
        op.drop_index(op.f('ix_device_efficiency_logs_station_id'), table_name='device_efficiency_logs')
        op.drop_index(op.f('ix_device_efficiency_logs_recorded_at'), table_name='device_efficiency_logs')
        op.drop_index(op.f('ix_device_efficiency_logs_metric_type'), table_name='device_efficiency_logs')
        op.drop_index(op.f('ix_device_efficiency_logs_log_date'), table_name='device_efficiency_logs')
        op.drop_index(op.f('ix_device_efficiency_logs_id'), table_name='device_efficiency_logs')
        op.drop_index(op.f('ix_device_efficiency_logs_device_id'), table_name='device_efficiency_logs')
        op.drop_table('device_efficiency_logs')
