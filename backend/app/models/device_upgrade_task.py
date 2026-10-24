"""设备级固件升级任务模型 (卡 43b26421)

与网关级 UpgradeTask (app/models/gateway.py, gateway_id 维度) 正交:
本表是设备维度 OTA 任务, 由 /devices/{id}/firmware/upgrade 下发。
"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceUpgradeTask(Base):
    """设备固件升级任务"""
    __tablename__ = "device_upgrade_tasks"

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)

    target_version = Column(String(50), nullable=False)  # 目标固件版本
    url = Column(String(500))  # 固件包地址 (可选, 缺省由设备侧按版本拉取)
    force = Column(Integer, default=0)  # 是否跳过版本匹配校验强制下发

    # 任务状态: pending, running, success, failed, cancelled
    status = Column(String(20), default="pending", nullable=False)
    progress = Column(Integer, default=0, nullable=False)  # 进度 0-100
    error_message = Column(Text)

    created_by = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
