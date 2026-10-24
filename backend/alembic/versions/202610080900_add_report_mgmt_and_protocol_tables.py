"""add report_mgmt / protocol_instances / parser_configs tables

Revision ID: 202610080900
Revises: 202610070100
Create Date: 2026-10-08 21:10:00

背景(2026-10-08 丁哥整站巡检):
- /report-mgmt 页 500: psycopg2 UndefinedTable "report_mgmt"
- /protocols 页 500: 同类缺表 protocol_instances / parser_configs
三张表由裸 SQL API 消费(app/api/v1/report_mgmt.py, protocol_instances.py)，
此前无 ORM 模型也无迁移 → 任何全新数据库都必缺表。
本迁移补齐；列序对齐 report_mgmt.py 的 SELECT * 位置访问(r[0]..r[11])。
config 字段以 json.dumps 字符串存 TEXT(与现有 INSERT 序列化一致)。
"""
from alembic import op
import sqlalchemy as sa

revision = '202610080900'
down_revision = '202610070100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 报告管理 — 列序不可变动(list_reports 按 SELECT * 位置取 r[0]..r[11])
    op.create_table(
        'report_mgmt',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=True),
        sa.Column('station_id', sa.Integer(), nullable=True),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='draft', nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('period_start', sa.String(length=20), nullable=True),
        sa.Column('period_end', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_report_mgmt_created_at', 'report_mgmt', ['created_at'])
    op.create_index('ix_report_mgmt_station_id', 'report_mgmt', ['station_id'])

    # 协议实例管理(Phase33 前端协议管理页)
    op.create_table(
        'protocol_instances',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('protocol_type', sa.String(length=50), nullable=True),
        sa.Column('gateway_id', sa.Integer(), nullable=True),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('parser_schema', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='stopped', nullable=True),
        sa.Column('connection_status', sa.String(length=20), server_default='disconnected', nullable=True),
        sa.Column('last_connected', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_protocol_instances_gateway_id', 'protocol_instances', ['gateway_id'])

    # 解析器配置(平台级共享模板)
    op.create_table(
        'parser_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('protocol', sa.String(length=50), nullable=True),
        sa.Column('parser_schema', sa.Text(), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('parser_configs')
    op.drop_table('protocol_instances')
    op.drop_table('report_mgmt')
