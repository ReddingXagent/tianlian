"""charger_qrcode: 桩编号 14 位 + gun_no 多枪粒度 (工作卡 c7523ad8 — 丁哥 01:00)

Revision ID: 202608070300
Revises: 202608070200
Create Date: 2026-08-07 03:00:00.000000

云快充协议 V1.6 改造 — DeviceQRCode 支持一桩多枪：
- 新增 gun_no 列（default=1，server_default='1'，nullable=False）；
- device_id 去列级唯一（旧 ix_device_qrcodes_device_id 为唯一索引 → 重建为非唯一）；
- 新增 (device_id, gun_no) 唯一索引 uq_device_qrcode_device_gun。

幂等: 用 inspector 判列/索引存在再改，兼容已 create_all 的环境。
旧 20 位 qr_code 记录保留（生成接口幂等覆盖为新 16 位枪号，旧码失效可接受）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070300"
down_revision: Union[str, Sequence[str], None] = "202608070200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "device_qrcodes"):
        return  # 表不存在时由 create_all 负责

    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("device_qrcodes")]
    indexes = inspector.get_indexes("device_qrcodes")

    # 1) 新增 gun_no 列（旧数据回填为 1）
    if "gun_no" not in columns:
        op.add_column(
            "device_qrcodes",
            sa.Column("gun_no", sa.Integer(), nullable=False, server_default="1"),
        )

    # 2) device_id 去唯一：旧 ix_device_qrcodes_device_id 为唯一索引 → drop 后重建非唯一
    dev_id_idx = next((ix for ix in indexes if ix.get("name") == "ix_device_qrcodes_device_id"), None)
    if dev_id_idx is not None and dev_id_idx.get("unique"):
        op.drop_index("ix_device_qrcodes_device_id", table_name="device_qrcodes")
        op.create_index("ix_device_qrcodes_device_id", "device_qrcodes", ["device_id"], unique=False)

    # 3) (device_id, gun_no) 唯一索引
    indexes_after = sa.inspect(bind).get_indexes("device_qrcodes")
    has_gun_uq = any(
        ix.get("name") == "uq_device_qrcode_device_gun" for ix in indexes_after
    )
    if not has_gun_uq:
        op.create_index(
            "uq_device_qrcode_device_gun",
            "device_qrcodes",
            ["device_id", "gun_no"],
            unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "device_qrcodes"):
        return

    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes("device_qrcodes")

    if any(ix.get("name") == "uq_device_qrcode_device_gun" for ix in indexes):
        op.drop_index("uq_device_qrcode_device_gun", table_name="device_qrcodes")

    # 恢复 device_id 唯一索引（注意：多枪数据下会冲突，仅空表/单枪时安全）
    dev_id_idx = next((ix for ix in indexes if ix.get("name") == "ix_device_qrcodes_device_id"), None)
    if dev_id_idx is not None and not dev_id_idx.get("unique"):
        op.drop_index("ix_device_qrcodes_device_id", table_name="device_qrcodes")
        op.create_index("ix_device_qrcodes_device_id", "device_qrcodes", ["device_id"], unique=True)

    # 防御性清理：若环境存在遗留的 gun_no 单列索引（早期模型 index=True 残留），drop 前先删
    if any(ix.get("name") == "ix_device_qrcodes_gun_no" for ix in indexes):
        op.drop_index("ix_device_qrcodes_gun_no", table_name="device_qrcodes")

    columns = [c["name"] for c in inspector.get_columns("device_qrcodes")]
    if "gun_no" in columns:
        op.drop_column("device_qrcodes", "gun_no")
