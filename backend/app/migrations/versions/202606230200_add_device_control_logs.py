"""add device_control_logs table

Revision ID: 202606230200
Revises: 202606230100
Create Date: 2026-06-23 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202606230200'
down_revision = '202606230100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'device_control_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False, index=True),
        sa.Column('device_name', sa.String(length=200), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False, index=True),
        sa.Column('parameter', sa.String(length=200), nullable=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('result', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('operator', sa.String(length=100), nullable=True),
        sa.Column('operator_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('device_control_logs')
