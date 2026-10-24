"""add_work_order_extensions

Revision ID: f0e1d2c3b4a5
Revises: 88377de16771
Create Date: 2026-07-23 19:40:00.000000

工单扩展：签到 / 支援请求 / 备件申请 / 评价 四张表
对应前端 workorderAPI: checkin / support / spare-parts / rate
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0e1d2c3b4a5'
down_revision: Union[str, Sequence[str], None] = '88377de16771'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # === 工单签到表 ===
    if not inspector.has_table('work_order_checkins'):
        op.create_table('work_order_checkins',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('order_id', sa.String(length=50), nullable=False),
            sa.Column('latitude', sa.Float(), nullable=True),
            sa.Column('longitude', sa.Float(), nullable=True),
            sa.Column('address', sa.String(length=255), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('photo_url', sa.String(length=500), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['work_orders.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_work_order_checkins_id'), 'work_order_checkins', ['id'], unique=False)
        op.create_index(op.f('ix_work_order_checkins_order_id'), 'work_order_checkins', ['order_id'], unique=False)
        op.create_index(op.f('ix_work_order_checkins_created_at'), 'work_order_checkins', ['created_at'], unique=False)

    # === 工单支援请求表 ===
    if not inspector.has_table('work_order_support_requests'):
        op.create_table('work_order_support_requests',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('order_id', sa.String(length=50), nullable=False),
            sa.Column('target_engineer_id', sa.Integer(), nullable=True),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('remote', sa.Boolean(), server_default=sa.text('0'), nullable=False),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['work_orders.id'], ),
            sa.ForeignKeyConstraint(['target_engineer_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_work_order_support_requests_id'), 'work_order_support_requests', ['id'], unique=False)
        op.create_index(op.f('ix_work_order_support_requests_order_id'), 'work_order_support_requests', ['order_id'], unique=False)
        op.create_index(op.f('ix_work_order_support_requests_created_at'), 'work_order_support_requests', ['created_at'], unique=False)

    # === 工单备件申请表 ===
    if not inspector.has_table('work_order_spare_parts'):
        op.create_table('work_order_spare_parts',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('order_id', sa.String(length=50), nullable=False),
            sa.Column('part_name', sa.String(length=100), nullable=False),
            sa.Column('part_model', sa.String(length=100), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), server_default='requested', nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['work_orders.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_work_order_spare_parts_id'), 'work_order_spare_parts', ['id'], unique=False)
        op.create_index(op.f('ix_work_order_spare_parts_order_id'), 'work_order_spare_parts', ['order_id'], unique=False)
        op.create_index(op.f('ix_work_order_spare_parts_created_at'), 'work_order_spare_parts', ['created_at'], unique=False)

    # === 工单评价表 ===
    if not inspector.has_table('work_order_ratings'):
        op.create_table('work_order_ratings',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('order_id', sa.String(length=50), nullable=False),
            sa.Column('response_rating', sa.Integer(), nullable=False),
            sa.Column('quality_rating', sa.Integer(), nullable=False),
            sa.Column('attitude_rating', sa.Integer(), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['order_id'], ['work_orders.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('order_id', name='uq_work_order_ratings_order_id'),
        )
        op.create_index(op.f('ix_work_order_ratings_id'), 'work_order_ratings', ['id'], unique=False)
        op.create_index(op.f('ix_work_order_ratings_order_id'), 'work_order_ratings', ['order_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('work_order_ratings'):
        op.drop_index(op.f('ix_work_order_ratings_order_id'), table_name='work_order_ratings')
        op.drop_index(op.f('ix_work_order_ratings_id'), table_name='work_order_ratings')
        op.drop_table('work_order_ratings')

    if inspector.has_table('work_order_spare_parts'):
        op.drop_index(op.f('ix_work_order_spare_parts_created_at'), table_name='work_order_spare_parts')
        op.drop_index(op.f('ix_work_order_spare_parts_order_id'), table_name='work_order_spare_parts')
        op.drop_index(op.f('ix_work_order_spare_parts_id'), table_name='work_order_spare_parts')
        op.drop_table('work_order_spare_parts')

    if inspector.has_table('work_order_support_requests'):
        op.drop_index(op.f('ix_work_order_support_requests_created_at'), table_name='work_order_support_requests')
        op.drop_index(op.f('ix_work_order_support_requests_order_id'), table_name='work_order_support_requests')
        op.drop_index(op.f('ix_work_order_support_requests_id'), table_name='work_order_support_requests')
        op.drop_table('work_order_support_requests')

    if inspector.has_table('work_order_checkins'):
        op.drop_index(op.f('ix_work_order_checkins_created_at'), table_name='work_order_checkins')
        op.drop_index(op.f('ix_work_order_checkins_order_id'), table_name='work_order_checkins')
        op.drop_index(op.f('ix_work_order_checkins_id'), table_name='work_order_checkins')
        op.drop_table('work_order_checkins')
