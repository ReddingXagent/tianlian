"""
管理后台 - 物联网接入: 终端管理 + 云服务配置 (SPEC §2.4)

- Terminal:     终端设备(摄像头/传感器/门禁), RTSP 流地址 + 录制配置 + 在线状态
- CloudConfig:  云平台连接配置(公有云/私有云), 存储桶 + 数据同步策略

注: 网关/设备库/协议管理见 app.models.gateway / device_library / protocol_instances,
    本模块聚焦管理后台的终端设备与云服务对接配置。
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, Index

from app.core.database import Base


# 取值白名单(便于前端筛选, 后端创建/更新时强制校验)
TERMINAL_TYPES = ("camera", "sensor", "access_control")
TERMINAL_STATUS = ("online", "offline", "maintenance")

CLOUD_PROVIDERS = ("cloud-a", "cloud-b", "aws", "private")
SYNC_STRATEGIES = ("realtime", "hourly", "daily")
CLOUD_CONFIG_STATUS = ("active", "inactive")


class Terminal(Base):
    """终端设备(摄像头/传感器/门禁)"""
    __tablename__ = "terminals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    terminal_code = Column(String(100), nullable=False, unique=True, comment="终端编号(唯一)")
    terminal_type = Column(String(30), nullable=False, comment="类型 camera/sensor/access_control")
    station_name = Column(String(200), nullable=True, comment="安装站点")
    ip_address = Column(String(50), nullable=True, comment="IP地址")
    rtsp_url = Column(String(500), nullable=True, comment="流地址 RTSP/RTMP")
    recording_config = Column(Text, nullable=True, comment="录制配置(JSON): enable/quality/retention_days")
    status = Column(String(20), default="offline", comment="状态 online/offline/maintenance")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_terminal_type", "terminal_type"),
        Index("idx_terminal_station", "station_name"),
        Index("idx_terminal_status", "status"),
    )


class CloudConfig(Base):
    """云平台连接配置(公有云/私有云)"""
    __tablename__ = "cloud_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_name = Column(String(100), nullable=False, comment="配置名称")
    provider = Column(String(30), nullable=False, comment="云提供商 cloud_provider/vendor_b/aws/private")
    config_json = Column(Text, nullable=True, comment="配置JSON: region/endpoint/access配置")
    bucket = Column(String(200), nullable=True, comment="存储桶")
    sync_strategy = Column(String(20), default="hourly", comment="数据同步策略 realtime/hourly/daily")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_cloud_provider", "provider"),
        Index("idx_cloud_sync", "sync_strategy"),
        Index("idx_cloud_status", "status"),
    )
