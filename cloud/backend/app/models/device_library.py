"""
设备型号库 ORM 模型 (admin-platform-spec §2.4)

光储充设备型号模板: 品牌/型号/类型/额定功率/技术参数模板/支持协议/规格书。
供管理后台「物联网接入 → 设备库」管理。
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceLibrary(Base):
    """设备型号库"""
    __tablename__ = "device_library"

    id = Column(Integer, primary_key=True, index=True)

    # 基础信息
    brand = Column(String(100), nullable=False, index=True)   # 设备品牌
    model = Column(String(100), nullable=False, index=True)   # 设备型号
    device_type = Column(String(50), nullable=False, index=True)
    # 设备类型: charger_dc / charger_ac / pv / battery / v2g

    # 技术参数
    rated_power_kw = Column(Float)        # 额定功率(kW)
    params_template = Column(JSON)        # 技术参数模板(键值对)
    supported_protocols = Column(JSON)    # 支持的协议编码列表

    # 规格书
    spec_url = Column(String(500))        # 规格书 URL

    # 状态
    status = Column(String(20), default="active", index=True)  # active / inactive

    created_at = Column(DateTime(timezone=True), server_default=func.now())
