"""add enterprise owner_team_id and enterprise_stations table

Revision ID: c3d4e5f6a7b8
Revises: f0e1d2c3b4a5
Create Date: 2026-07-23 22:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'f0e1d2c3b4a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Enterprise 加 owner_team_id
    if inspector.has_table('enterprises'):
        existing_cols = {c['name'] for c in inspector.get_columns('enterprises')}
        if 'owner_team_id' not in existing_cols:
            with op.batch_alter_table('enterprises', schema=None) as batch_op:
                batch_op.add_column(sa.Column('owner_team_id', sa.Integer(), nullable=True, comment='经营团队ID'))
                batch_op.create_index('idx_enterprise_owner_team', ['owner_team_id'], unique=False)

    # 2. 新表 enterprise_stations (多对多)
    if not inspector.has_table('enterprise_stations'):
        op.create_table(
            'enterprise_stations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('enterprise_id', sa.Integer(), sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
        op.create_index('idx_enterprise_station_unique', 'enterprise_stations', ['enterprise_id', 'station_id'], unique=True)
        op.create_index('ix_enterprise_stations_enterprise_id', 'enterprise_stations', ['enterprise_id'])
        op.create_index('ix_enterprise_stations_station_id', 'enterprise_stations', ['station_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('enterprise_stations'):
        op.drop_index('ix_enterprise_stations_station_id', table_name='enterprise_stations')
        op.drop_index('ix_enterprise_stations_enterprise_id', table_name='enterprise_stations')
        op.drop_index('idx_enterprise_station_unique', table_name='enterprise_stations')
        op.drop_table('enterprise_stations')

    if inspector.has_table('enterprises'):
        existing_cols = {c['name'] for c in inspector.get_columns('enterprises')}
        if 'owner_team_id' in existing_cols:
            try:
                with op.batch_alter_table('enterprises', schema=None) as batch_op:
                    batch_op.drop_index('idx_enterprise_owner_team')
                    batch_op.drop_column('owner_team_id')
            except Exception:
                pass  # Best-effort: batch_alter_table on SQLite may fail with model_defined indexes
