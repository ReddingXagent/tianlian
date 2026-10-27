"""add device_config table

Revision ID: 202606230300
Revises: 202606230200
Create Date: 2026-06-23 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202606230300'
down_revision = '202606230200'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'device_configs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('device_id', sa.BigInteger(), nullable=False),
        sa.Column('voltage_limit', sa.Float(), nullable=False, server_default='420.0'),
        sa.Column('current_limit', sa.Float(), nullable=False, server_default='60.0'),
        sa.Column('max_power', sa.Float(), nullable=False, server_default='60.0'),
        sa.Column('charge_mode', sa.Enum('fast', 'smart', 'eco', name='chargemode'), nullable=False, server_default='smart'),
        sa.Column('overload_protection', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('time_periods', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('device_id', name='uq_device_config_device_id'),
    )
    op.create_index('ix_device_configs_device_id', 'device_configs', ['device_id'])


def downgrade() -> None:
    op.drop_index('ix_device_configs_device_id', table_name='device_configs')
    op.drop_table('device_configs')
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS chargemode")