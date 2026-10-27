"""
运营平台 - 市政监管对接模型 (SPEC §2.5, 迁移自 admin → ops)

对接市政充电监管平台, 上报站点/设备/订单数据并做合规检查。
- MunicipalSupervisionConfig: 监管平台配置(城市/URL/认证/上报策略) — 按运营团队隔离
- RegulatoryReport:            上报记录(类型/状态/重试)
- ComplianceCheck:             合规检查记录
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, Index

from app.core.database import Base


REPORT_TYPES = ("station", "device", "order", "heartbeat")
REPORT_STRATEGIES = ("scheduled", "realtime")
REPORT_STATUS = ("success", "failed", "pending")
CHECK_TYPES = ("data_integrity", "report_delay", "compliance")
CHECK_RESULTS = ("pass", "warn", "fail")
CONFIG_STATUS = ("active", "inactive")
# 市政监管平台类型
PLATFORM_TYPES = ("yueyichong", "lianlian", "zhelichong", "generic", "other")
PROTOCOL_TYPES = ("http_push", "http_pull", "mqtt", "websocket")


class MunicipalSupervisionConfig(Base):
    """市政监管平台配置 — 按运营团队隔离"""
    __tablename__ = "municipal_supervision_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, default=0, comment="运营团队ID (0=平台默认模板)")
    city = Column(String(100), nullable=False, comment="对接城市")
    city_code = Column(String(20), nullable=True, comment="城市编码")
    platform_name = Column(String(100), nullable=True, comment="平台名称(粤易充/联联/浙里充等)")
    platform_type = Column(String(50), default="generic", comment="平台类型 yueyichong/lianlian/zhelichong/generic/other")
    protocol_type = Column(String(30), default="http_push", comment="协议类型 http_push/http_pull/mqtt/websocket")
    platform_url = Column(String(500), nullable=False, comment="监管平台URL")
    auth_config = Column(Text, nullable=True, comment="认证配置(JSON): data接口/auth接口凭证")
    report_strategy = Column(String(20), default="scheduled", comment="上报策略 scheduled/realtime")
    report_interval_seconds = Column(Integer, default=60, comment="定时上报间隔(秒)")
    station_endpoints = Column(Text, nullable=True, comment="各上报端点配置(JSON): station/device/order/heartbeat")
    heartbeat_enabled = Column(Integer, default=1, comment="心跳保活 1/0")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_msuperteam", "team_id"),
        Index("idx_msupercity", "city"),
        Index("idx_msuperstatus", "status"),
    )


class RegulatoryReport(Base):
    """监管数据上报记录 — 继承配置的团队维度"""
    __tablename__ = "regulatory_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, default=0, comment="运营团队ID (冗余)")
    config_id = Column(Integer, nullable=False, comment="关联 municipal_supervision_configs.id")
    city = Column(String(100), nullable=True, comment="城市(冗余,便于筛选)")
    report_type = Column(String(20), nullable=False, comment="上报类型 station/device/order/heartbeat")
    report_content = Column(Text, nullable=True, comment="上报内容(JSON)")
    status = Column(String(20), default="pending", comment="状态 success/failed/pending")
    retry_count = Column(Integer, default=0, comment="重试次数")
    error_message = Column(String(500), nullable=True, comment="失败错误信息")
    reported_at = Column(DateTime, nullable=True, comment="实际上报时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_rreport_team", "team_id"),
        Index("idx_rreport_config", "config_id"),
        Index("idx_rreport_type", "report_type"),
        Index("idx_rreport_status", "status"),
    )


class ComplianceCheck(Base):
    """监管合规检查记录 — 继承配置的团队维度"""
    __tablename__ = "compliance_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, default=0, comment="运营团队ID (冗余)")
    config_id = Column(Integer, nullable=False, comment="关联 municipal_supervision_configs.id")
    city = Column(String(100), nullable=True, comment="城市(冗余)")
    check_type = Column(String(30), nullable=False, comment="检查类型 data_integrity/report_delay/compliance")
    result = Column(String(20), nullable=False, default="pass", comment="结果 pass/warn/fail")
    score = Column(Numeric(5, 2), default=Decimal("0.00"), comment="合规得分(0-100)")
    details = Column(Text, nullable=True, comment="检查明细(JSON)")
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="检查时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_cca_team", "team_id"),
        Index("idx_cca_config", "config_id"),
        Index("idx_cca_result", "result"),
    )
