"""add notification_configs, notification_templates, notification_logs

Revision ID: 202606230100
Revises: 202606040100
Create Date: 2026-06-23 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202606230100'
down_revision = '202606040100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 通知配置表
    op.create_table(
        'notification_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('scope_type', sa.String(length=20), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('app_push_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('im_b_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('im_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('receivers', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('receiver_roles', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('trigger_events', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('template_overrides', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('quiet_start', sa.String(length=5), nullable=True),
        sa.Column('quiet_end', sa.String(length=5), nullable=True),
        sa.Column('timezone', sa.String(length=50), server_default='Asia/Shanghai'),
        sa.Column('rate_limit_per_hour', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('rate_limit_per_day', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_configs_scope', 'notification_configs', ['scope_type', 'scope_id'], unique=False)
    op.create_index('ix_notification_configs_enabled', 'notification_configs', ['enabled'], unique=False)

    # 通知模板表
    op.create_table(
        'notification_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_templates_code', 'notification_templates', ['code'], unique=True)

    # 通知发送日志表
    op.create_table(
        'notification_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_id', sa.String(length=100), nullable=True),
        sa.Column('event_data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('template_code', sa.String(length=50), nullable=True),
        sa.Column('receiver_type', sa.String(length=20), nullable=False),
        sa.Column('receiver_id', sa.String(length=100), nullable=False),
        sa.Column('receiver_name', sa.String(length=100), nullable=True),
        sa.Column('subject', sa.String(length=200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_response', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['notification_configs.id'], ),
        sa.ForeignKeyConstraint(['template_id'], ['notification_templates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_logs_event', 'notification_logs', ['event_type', 'event_id'], unique=False)
    op.create_index('ix_notification_logs_status_time', 'notification_logs', ['status', 'created_at'], unique=False)
    op.create_index('ix_notification_logs_receiver', 'notification_logs', ['receiver_type', 'receiver_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notification_logs_receiver', table_name='notification_logs')
    op.drop_index('ix_notification_logs_status_time', table_name='notification_logs')
    op.drop_index('ix_notification_logs_event', table_name='notification_logs')
    op.drop_table('notification_logs')
    op.drop_index('ix_notification_templates_code', table_name='notification_templates')
    op.drop_table('notification_templates')
    op.drop_index('ix_notification_configs_enabled', table_name='notification_configs')
    op.drop_index('ix_notification_configs_scope', table_name='notification_configs')
    op.drop_table('notification_configs')