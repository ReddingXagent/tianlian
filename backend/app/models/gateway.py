"""
天链 V3 - 网关模型
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class Gateway(Base):
    """网关设备模型"""
    __tablename__ = "gateways"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    sn = Column(String(50), unique=True, index=True, nullable=False)  # 网关序列号
    name = Column(String(100), nullable=False)  # 网关名称
    model = Column(String(50))  # 网关型号
    manufacturer = Column(String(50))  # 制造商
    
    # 关联站点
    station_id = Column(Integer, index=True)
    
    # 网关状态
    status = Column(String(20), default="offline")  # online, offline, maintenance, fault
    firmware_version = Column(String(20))  # 固件版本
    last_online = Column(DateTime)  # 最后在线时间
    
    # 网络信息
    ip_address = Column(String(50))  # IP地址
    mac_address = Column(String(50))  # MAC地址
    
    # 位置信息
    location = Column(String(200))  # 安装位置
    
    # 健康状态
    health_score = Column(Float, default=100.0)  # 健康评分 0-100
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 备注
    notes = Column(Text)

    # 关系
    devices = relationship("Device", back_populates="gateway")


class GatewaySN(Base):
    """网关SN码管理模型"""
    __tablename__ = "gateway_sn"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    sn = Column(String(50), unique=True, index=True, nullable=False)  # SN码
    model = Column(String(50), nullable=False)  # 网关型号
    
    # SN码状态
    status = Column(String(20), default="generated")  # generated, written, activated, locked, recalled
    batch_no = Column(String(50))  # 批次号
    
    # 关联信息
    gateway_id = Column(Integer)  # 关联网关ID
    station_id = Column(Integer)  # 关联站点ID
    team_id = Column(Integer)  # 所属团队
    
    # 时间戳
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # 生成时间
    written_at = Column(DateTime)  # 写入时间
    activated_at = Column(DateTime)  # 激活时间
    locked_at = Column(DateTime)  # 锁定时间
    recalled_at = Column(DateTime)  # 召回时间
    
    # 操作人
    generated_by = Column(Integer)  # 生成人
    written_by = Column(Integer)  # 写入人
    activated_by = Column(Integer)  # 激活人
    
    # 备注
    notes = Column(Text)


class Firmware(Base):
    """固件版本管理模型"""
    __tablename__ = "firmware"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    version = Column(String(20), unique=True, nullable=False)  # 版本号
    model = Column(String(50), nullable=False)  # 适用型号
    file_path = Column(String(200))  # 文件路径
    file_size = Column(Integer)  # 文件大小(bytes)
    checksum = Column(String(100))  # 文件校验
    
    # 版本信息
    changelog = Column(Text)  # 更新日志
    release_date = Column(DateTime)  # 发布日期
    status = Column(String(20), default="draft")  # draft, released, deprecated
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 操作人
    created_by = Column(Integer)


class UpgradeTask(Base):
    """固件升级任务模型"""
    __tablename__ = "upgrade_tasks"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    gateway_id = Column(BigInteger, nullable=False)  # 目标网关
    firmware_id = Column(BigInteger, nullable=False)  # 目标固件
    
    # 任务状态
    status = Column(String(20), default="pending")  # pending, running, success, failed, cancelled
    progress = Column(Integer, default=0)  # 进度 0-100
    
    # 执行信息
    start_time = Column(DateTime)  # 开始时间
    end_time = Column(DateTime)  # 结束时间
    error_message = Column(Text)  # 错误信息
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 操作人
    created_by = Column(Integer)  # 创建人