"""
运营平台 - 互联互通对接模型 (SPEC §2.5, 迁移自 admin → ops)

对接第三方充电平台(华为/国网/南网/特来电等)的导流订单与分成。
- InterconnectConfig: 平台接入配置(认证/同步/分成) — 按运营团队隔离
- InterconnectOrder:  他平台导流订单

注: 互联互通【结算】见 app.models.ops_settlement.InterconnectSettlement,
    本模块聚焦运营平台的接入配置与订单查询。
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, Index

from app.core.database import Base


# 平台编码白名单(便于前端筛选, 后端不强制枚举以兼容新平台)
PLATFORM_CODES = ("huawei", "sgcc", "csg", "teld", "other")
AUTH_TYPES = ("apikey", "oauth")
CONFIG_STATUS = ("active", "inactive")
ORDER_STATUS = ("synced", "settled", "conflict")
# 中电联协议版本
PROTOCOL_VERSIONS = ("V1.0", "V1.6", "V2.0")
SYNC_DIRECTIONS = ("push", "pull", "bidirectional")


class InterconnectConfig(Base):
    """互联互通平台接入配置 — 按运营团队隔离"""
    __tablename__ = "interconnect_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, default=0, comment="运营团队ID (0=平台默认模板)")
    platform_name = Column(String(100), nullable=False, comment="平台名称")
    platform_code = Column(String(50), nullable=False, comment="平台编码 huawei/sgcc/csg/teld/other")
    api_base_url = Column(String(500), nullable=False, comment="API接入地址")
    auth_type = Column(String(20), nullable=False, default="apikey", comment="认证方式 apikey/oauth")
    auth_params = Column(Text, nullable=True, comment="认证参数(JSON): apikey/oauth 配置")
    revenue_share_ratio = Column(Numeric(5, 4), default=Decimal("0.0000"), comment="我方分成比例(0.7000=70%)")
    data_sync_interval = Column(Integer, default=300, comment="数据同步间隔(秒)")
    protocol_version = Column(String(20), nullable=True, comment="中电联协议版本 V1.0/V1.6/V2.0")
    sync_direction = Column(String(20), default="pull", comment="同步方向 push/pull/bidirectional")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_iconfig_team", "team_id"),
        Index("idx_iconfig_code", "platform_code"),
        Index("idx_iconfig_status", "status"),
    )


class InterconnectOrder(Base):
    """互联互通导流订单(他平台同步过来) — 继承配置的团队维度"""
    __tablename__ = "interconnect_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, default=0, comment="运营团队ID (冗余,便于按团队筛选)")
    platform_id = Column(Integer, nullable=False, comment="关联 interconnect_configs.id")
    platform_code = Column(String(50), nullable=False, comment="来源平台编码(冗余,便于筛选)")
    outer_order_id = Column(String(100), nullable=False, comment="外部订单号")
    outer_user_id = Column(String(100), nullable=True, comment="外部用户标识")
    station_id = Column(String(100), nullable=True, comment="站点标识")
    device_id = Column(String(100), nullable=True, comment="设备标识")
    charge_energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="充电量(kWh)")
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="订单总费用(元)")
    our_share = Column(Numeric(12, 2), default=Decimal("0.00"), comment="我方分成(元)")
    partner_share = Column(Numeric(12, 2), default=Decimal("0.00"), comment="合作方分成(元)")
    status = Column(String(20), default="synced", comment="状态 synced/settled/conflict")
    synced_at = Column(DateTime, nullable=True, comment="同步时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_iorder_team", "team_id"),
        Index("idx_iorder_platform", "platform_id", "platform_code"),
        Index("idx_iorder_outer", "outer_order_id"),
        Index("idx_iorder_status", "status"),
    )
