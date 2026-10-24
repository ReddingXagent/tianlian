"""add device provision/credential cols + station approval_status

任务卡 1256e7fa：建站加设备自助闭环。

- Device: provision_status / charge_box_id / mqtt_username / mqtt_password / auth_token
- Station: approval_status (default approved)

Revision ID: 202608080100
Revises: 202606230300
Create Date: 2026-08-08 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202608080100'
down_revision = '202606230300'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Device: 入网状态 + 接入凭证 ──
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'provision_status',
            sa.Enum('unprovisioned', 'provisioning', 'online', name='provisionstatus'),
            nullable=False,
            server_default='unprovisioned',
        ))
        batch_op.add_column(sa.Column('charge_box_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('mqtt_username', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('mqtt_password', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('auth_token', sa.String(length=200), nullable=True))
        batch_op.create_index('ix_devices_provision_status', ['provision_status'])
        batch_op.create_index('ix_devices_charge_box_id', ['charge_box_id'])
        batch_op.create_index('ix_devices_mqtt_username', ['mqtt_username'])

    # ── Station: 审核状态 ──
    with op.batch_alter_table('stations', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'approval_status',
            sa.Enum('approved', 'pending', 'rejected', name='approvalstatus'),
            nullable=False,
            server_default='approved',
        ))
        batch_op.create_index('ix_stations_approval_status', ['approval_status'])


def downgrade() -> None:
    with op.batch_alter_table('stations', schema=None) as batch_op:
        batch_op.drop_index('ix_stations_approval_status')
        batch_op.drop_column('approval_status')

    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_index('ix_devices_mqtt_username')
        batch_op.drop_index('ix_devices_charge_box_id')
        batch_op.drop_index('ix_devices_provision_status')
        batch_op.drop_column('auth_token')
        batch_op.drop_column('mqtt_password')
        batch_op.drop_column('mqtt_username')
        batch_op.drop_column('charge_box_id')
        batch_op.drop_column('provision_status')

    op.execute("DROP TYPE IF EXISTS provisionstatus")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
