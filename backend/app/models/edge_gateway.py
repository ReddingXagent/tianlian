"""
天链 V3 - 边缘网关 SN 平台化管理模型 (任务卡 e940c9f4)

平台提供方同时提供边缘网关硬件，其 SN 在平台管理界面操作管理。
EdgeGateway 追踪"网关硬件入库 → 出库/发货 → 绑定场站 → 在线运行 → 退役"
全生命周期库存状态，与运行态的 ``Gateway`` (online/offline/fault 设备表) 正交：

- ``Gateway``      场站内运行态控制器 (聚合桩/光储/车牌识别上报), 关注实时状态。
- ``EdgeGateway``  平台硬件发货台账 (SN 批量生成/库存/绑定/退役), 关注生命周期。

状态机::

    inventory ──ship──▶ shipped ──bind──▶ bound ──online──▶ online
       │                   │                 │                │
       └───────────────────┴─────────────────┴────────────────┴──▶ decommissioned
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    DateTime,
    Index,
    CheckConstraint,
)

from app.core.database import Base


# ── SN 生命周期状态 ──
EDGE_GATEWAY_STATUS_INVENTORY = "inventory"      # 入库 (SN 已生成, 待发货)
EDGE_GATEWAY_STATUS_SHIPPED = "shipped"          # 已出库/发货 (在途, 未绑定场站)
EDGE_GATEWAY_STATUS_BOUND = "bound"              # 已绑定场站 (待上线)
EDGE_GATEWAY_STATUS_ONLINE = "online"            # 在线运行 (网关已连上平台)
EDGE_GATEWAY_STATUS_DECOMMISSIONED = "decommissioned"  # 退役 (停用/报废)

# 合法状态集合 (与迁移 CHECK 约束字面值一致)
EDGE_GATEWAY_STATUS_VALUES = (
    EDGE_GATEWAY_STATUS_INVENTORY,
    EDGE_GATEWAY_STATUS_SHIPPED,
    EDGE_GATEWAY_STATUS_BOUND,
    EDGE_GATEWAY_STATUS_ONLINE,
    EDGE_GATEWAY_STATUS_DECOMMISSIONED,
)


class EdgeGateway(Base):
    """边缘网关 SN 平台台账 (任务卡 e940c9f4)"""

    __tablename__ = "edge_gateways"

    id = Column(BigInteger, primary_key=True, index=True)  # BigInt 防溢出

    # ── SN 标识 ──
    # G 类 9 位: 类型码(G) + 区域码(2) + 序号(6), 由 CodeGenerator.generate_gateway_sn 生成
    sn = Column(String(50), unique=True, index=True, nullable=False)
    # 批次号 (批量生成时指定, 便于按批追溯)
    batch = Column(String(50), index=True, nullable=True)

    # ── 生命周期状态 ──
    # inventory/shipped/bound/online/decommissioned (见 EDGE_GATEWAY_STATUS_VALUES)
    status = Column(String(20), default=EDGE_GATEWAY_STATUS_INVENTORY, nullable=False)

    # ── 关联场站 (绑定后非空) ──
    station_id = Column(Integer, index=True, nullable=True)

    # ── 固件/在线 ──
    firmware_version = Column(String(50), nullable=True)            # 当前固件版本
    last_online_at = Column(DateTime, nullable=True)                # 首次/最近上线时间 (接入钩子更新)

    # ── 时间戳 ──
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        # 状态值约束 (字面值与 EDGE_GATEWAY_STATUS_VALUES 一致, 防脏数据)
        CheckConstraint(
            "status IN ('inventory', 'shipped', 'bound', 'online', 'decommissioned')",
            name="ck_edge_gateways_status",
        ),
        # 复合索引: 状态 + 批次 (库存/状态筛选 + 按批统计的高频查询)
        Index("ix_edge_gateways_status_batch", "status", "batch"),
    )
