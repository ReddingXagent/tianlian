"""add escalation_timeout_minutes to alarm_rules

Revision ID: 202606040100
Revises: 202606020200
Create Date: 2026-06-04 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202606040100'
down_revision = '202606020200'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 告警规则增加升级超时配置
    op.add_column('alarm_rules', sa.Column(
        'escalation_timeout_minutes',
        sa.Integer(),
        nullable=True,
        server_default='30',
        comment='超时未处理自动升级的分钟数 (WARN→ERROR 30min, ERROR→CRITICAL 15min)'
    ))
    # 告警表增加升级来源字段
    op.add_column('alarms', sa.Column(
        'escalated_from',
        sa.String(length=20),
        nullable=True,
        comment='从哪个级别升级而来 (warn→error, error→critical)'
    ))
    op.add_column('alarms', sa.Column(
        'escalated_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='升级时间'
    ))
    op.add_column('alarms', sa.Column(
        'original_level',
        sa.String(length=20),
        nullable=True,
        comment='原始告警级别（升级前）'
    ))
    op.add_column('alarms', sa.Column(
        'aggregation_count',
        sa.Integer(),
        nullable=True,
        server_default='1',
        comment='聚合告警计数'
    ))
    op.add_column('alarms', sa.Column(
        'aggregation_first_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='聚合首条告警时间'
    ))
    op.add_column('alarms', sa.Column(
        'aggregation_last_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='聚合末条告警时间'
    ))


def downgrade() -> None:
    op.drop_column('alarms', 'aggregation_last_at')
    op.drop_column('alarms', 'aggregation_first_at')
    op.drop_column('alarms', 'aggregation_count')
    op.drop_column('alarms', 'original_level')
    op.drop_column('alarms', 'escalated_at')
    op.drop_column('alarms', 'escalated_from')
    op.drop_column('alarm_rules', 'escalation_timeout_minutes')