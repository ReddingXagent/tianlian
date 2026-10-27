"""add_device_library_and_protocols

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-07-25 21:00:00.000000

物联网接入 (admin-platform-spec §2.4):
- device_library:   设备型号库(品牌/型号/类型/额定功率/参数模板/支持协议/规格书)
- device_protocols: 通信协议(OCPP/Modbus/MQTT/HTTP/自定义 + 数据点映射), code 唯一
- protocol_rules:   协议解析规则(上行 parse_rule / 下行 encode_rule), FK→device_protocols

幂等: 用 inspector 判表存在再建，兼容已 create_all 的环境。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'h5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # ── 设备型号库 ──
    if not _has_table(bind, 'device_library'):
        op.create_table(
            'device_library',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('brand', sa.String(length=100), nullable=False),
            sa.Column('model', sa.String(length=100), nullable=False),
            sa.Column('device_type', sa.String(length=50), nullable=False),
            sa.Column('rated_power_kw', sa.Float(), nullable=True),
            sa.Column('params_template', sa.JSON(), nullable=True),
            sa.Column('supported_protocols', sa.JSON(), nullable=True),
            sa.Column('spec_url', sa.String(length=500), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_device_library_id', 'device_library', ['id'])
        op.create_index('ix_device_library_brand', 'device_library', ['brand'])
        op.create_index('ix_device_library_model', 'device_library', ['model'])
        op.create_index('ix_device_library_device_type', 'device_library', ['device_type'])
        op.create_index('ix_device_library_status', 'device_library', ['status'])

    # ── 通信协议 ──
    if not _has_table(bind, 'device_protocols'):
        op.create_table(
            'device_protocols',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('type', sa.String(length=20), nullable=False),
            sa.Column('version', sa.String(length=50), nullable=True),
            sa.Column('protocol_definition', sa.JSON(), nullable=True),
            sa.Column('data_point_mappings', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code', name='uq_device_protocols_code'),
        )
        op.create_index('ix_device_protocols_id', 'device_protocols', ['id'])
        op.create_index('ix_device_protocols_code', 'device_protocols', ['code'])
        op.create_index('ix_device_protocols_type', 'device_protocols', ['type'])
        op.create_index('ix_device_protocols_status', 'device_protocols', ['status'])

    # ── 协议解析规则 ──
    if not _has_table(bind, 'protocol_rules'):
        op.create_table(
            'protocol_rules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('protocol_id', sa.Integer(), nullable=False),
            sa.Column('direction', sa.String(length=20), nullable=False),
            sa.Column('message_type', sa.String(length=100), nullable=True),
            sa.Column('parse_rule', sa.JSON(), nullable=True),
            sa.Column('encode_rule', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(['protocol_id'], ['device_protocols.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_protocol_rules_id', 'protocol_rules', ['id'])
        op.create_index('ix_protocol_rules_protocol_id', 'protocol_rules', ['protocol_id'])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, 'protocol_rules'):
        op.drop_index('ix_protocol_rules_protocol_id', table_name='protocol_rules')
        op.drop_index('ix_protocol_rules_id', table_name='protocol_rules')
        op.drop_table('protocol_rules')
    if _has_table(bind, 'device_protocols'):
        op.drop_index('ix_device_protocols_status', table_name='device_protocols')
        op.drop_index('ix_device_protocols_type', table_name='device_protocols')
        op.drop_index('ix_device_protocols_code', table_name='device_protocols')
        op.drop_index('ix_device_protocols_id', table_name='device_protocols')
        op.drop_table('device_protocols')
    if _has_table(bind, 'device_library'):
        op.drop_index('ix_device_library_status', table_name='device_library')
        op.drop_index('ix_device_library_device_type', table_name='device_library')
        op.drop_index('ix_device_library_model', table_name='device_library')
        op.drop_index('ix_device_library_brand', table_name='device_library')
        op.drop_index('ix_device_library_id', table_name='device_library')
        op.drop_table('device_library')
