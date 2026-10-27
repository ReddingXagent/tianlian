"""invoice_platform_configs: 开票平台 OAuth/RSA 字段扩展 (电子发票自动开票)

Revision ID: 202608070500
Revises: 202608070400
Create Date: 2026-08-07 05:00:00.000000

InvoicePlatformConfig 新增 6 列 (均 nullable), 支撑诺诺/百旺/航信自动开票:
- access_token_url  换取 access_token 的 URL
- private_key_enc   RSA 私钥 (Fernet 加密存储, 读取时解密)
- device_no         设备/终端编号
- callback_url      开票结果回调地址
- ext_config_json   平台特有扩展字段 (JSON)
- token_cache_json  运行时缓存 access_token + 过期时间 (JSON)

PG 原生 ADD COLUMN; SQLite batch_alter_table 表重建, 两种 dialect 均安全。
全列 nullable, 历史数据无值; _has_column 守卫保证幂等 (与 create_all 基线共存不冲突)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608070500"
down_revision: Union[str, Sequence[str], None] = "202608070400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = [
    ("access_token_url", sa.String(length=500)),
    ("private_key_enc", sa.Text()),
    ("device_no", sa.String(length=100)),
    ("callback_url", sa.String(length=500)),
    ("ext_config_json", sa.Text()),
    ("token_cache_json", sa.Text()),
]


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("invoice_platform_configs"):
        # 表缺失(单表隔离库) -> 优雅跳过
        return
    for name, coltype in _NEW_COLUMNS:
        if not _has_column(bind, "invoice_platform_configs", name):
            with op.batch_alter_table("invoice_platform_configs") as batch_op:
                batch_op.add_column(sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("invoice_platform_configs"):
        # 表缺失 -> 无列可删, 优雅跳过
        return
    for name, _ in reversed(_NEW_COLUMNS):
        if _has_column(bind, "invoice_platform_configs", name):
            with op.batch_alter_table("invoice_platform_configs") as batch_op:
                batch_op.drop_column(name)
