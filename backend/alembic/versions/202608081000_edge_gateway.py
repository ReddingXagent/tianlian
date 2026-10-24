"""edge_gateway: 边缘网关 SN 平台台账表 (任务卡 e940c9f4)

Revision ID: 202608081000
Revises: 202608080900
Create Date: 2026-08-08 10:00:00.000000

平台提供方同时提供边缘网关硬件, 其 SN 在平台管理界面操作管理。
本表追踪网关硬件发货台账生命周期 (inventory → shipped → bound → online → decommissioned),
与运行态 gateways 表 (online/offline/fault 设备) 正交。

字段:
- sn:        G 类 9 位 (G + 区域码2 + 序号6), CodeGenerator 生成, unique
- batch:     批次号 (按批追溯)
- status:    生命周期状态 (CHECK 约束限定 5 值)
- station_id: 绑定场站 (可空)
- firmware_version / last_online_at: 在线信息 (接入钩子更新)

索引: sn(unique) / status / station_id / batch + 复合 (status, batch)

幂等建表: inspector 判表存在再建, 兼容已 create_all 的测试环境
(与 parking_integration / occupancy_events 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608081000"
down_revision: Union[str, Sequence[str], None] = "202608080900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 状态字面值 (与 app.models.edge_gateway.EDGE_GATEWAY_STATUS_VALUES 一致)
_STATUS_VALUES = (
    "inventory",
    "shipped",
    "bound",
    "online",
    "decommissioned",
)


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "edge_gateways"):
        return

    op.create_table(
        "edge_gateways",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sn", sa.String(length=50), nullable=False),
        sa.Column("batch", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="inventory"),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column("last_online_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint(
            "status IN ('inventory', 'shipped', 'bound', 'online', 'decommissioned')",
            name="ck_edge_gateways_status",
        ),
    )
    op.create_index("ix_edge_gateways_sn", "edge_gateways", ["sn"], unique=True)
    op.create_index("ix_edge_gateways_status", "edge_gateways", ["status"])
    op.create_index("ix_edge_gateways_station_id", "edge_gateways", ["station_id"])
    op.create_index("ix_edge_gateways_batch", "edge_gateways", ["batch"])
    op.create_index("ix_edge_gateways_status_batch", "edge_gateways", ["status", "batch"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "edge_gateways"):
        return
    op.drop_index("ix_edge_gateways_status_batch", table_name="edge_gateways")
    op.drop_index("ix_edge_gateways_batch", table_name="edge_gateways")
    op.drop_index("ix_edge_gateways_station_id", table_name="edge_gateways")
    op.drop_index("ix_edge_gateways_status", table_name="edge_gateways")
    op.drop_index("ix_edge_gateways_sn", table_name="edge_gateways")
    op.drop_table("edge_gateways")
