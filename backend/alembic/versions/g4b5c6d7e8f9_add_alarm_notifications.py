"""add_alarm_notifications

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-25 19:00:00.000000

告警通知发送记录 (maint-platform-spec §2.1):
- alarm_notifications: 每次告警通知发送（sms/app/email/im/im_b）写一条记录，
  由 notification_sender.send_alarm_notification 落库，
  供 GET /api/v1/alarms/{id}/notifications 审计查询。

幂等: 用 inspector 判表存在再建，兼容已 create_all 的环境。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, 'alarm_notifications'):
        op.create_table(
            'alarm_notifications',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('alarm_id', sa.BigInteger(), nullable=False),
            sa.Column('channel', sa.String(length=20), nullable=False),
            sa.Column('recipient', sa.String(length=200), nullable=True),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('result', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_alarm_notifications_id', 'alarm_notifications', ['id'])
        op.create_index('ix_alarm_notifications_alarm_id', 'alarm_notifications', ['alarm_id'])
        op.create_index('ix_alarm_notifications_status', 'alarm_notifications', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, 'alarm_notifications'):
        op.drop_index('ix_alarm_notifications_status', table_name='alarm_notifications')
        op.drop_index('ix_alarm_notifications_alarm_id', table_name='alarm_notifications')
        op.drop_index('ix_alarm_notifications_id', table_name='alarm_notifications')
        op.drop_table('alarm_notifications')
