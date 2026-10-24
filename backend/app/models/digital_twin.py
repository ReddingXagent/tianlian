"""
数字孪生模型 - 3D可视化配置
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class ThreeDModelType(str, enum.Enum):
    """3D模型类型"""
    SOLAR_INVERTER = "solar_inverter"      # 光伏逆变器
    BATTERY_INVERTER = "battery_inverter"  # 储能逆变器
    PCS = "pcs"                            # 储能变流器
    BATTERY_RACK = "battery_rack"          # 电池柜
    CHARGER_DC = "charger_dc"              # 直流充电桩
    CHARGER_AC = "charger_ac"              # 交流充电桩
    GATEWAY = "gateway"                    # 网关
    METER = "meter"                        # 电表
    TRANSFORMER = "transformer"            # 变压器
    PANEL = "panel"                        # 配电盘

class DigitalTwinModel(Base):
    """设备3D模型配置表"""
    __tablename__ = "digital_twin_models"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), unique=True, nullable=False, index=True)
    
    # 3D模型配置
    model_type = Column(SQLEnum(ThreeDModelType), nullable=False, index=True)
    scale_x = Column(Float, default=1.0)      # X轴缩放
    scale_y = Column(Float, default=1.0)      # Y轴缩放
    scale_z = Column(Float, default=1.0)      # Z轴缩放
    position_x = Column(Float, default=0.0)   # X轴位置
    position_y = Column(Float, default=0.0)   # Y轴位置
    position_z = Column(Float, default=0.0)   # Z轴位置
    rotation_x = Column(Float, default=0.0)   # X轴旋转（弧度）
    rotation_y = Column(Float, default=0.0)   # Y轴旋转（弧度）
    rotation_z = Column(Float, default=0.0)   # Z轴旋转（弧度）
    
    # 材质颜色配置（RGBA）
    color_primary = Column(String(20), default="#1890ff")      # 主色
    color_secondary = Column(String(20), default="#52c41a")    # 次要色
    color_accent = Column(String(20), default="#faad14")       # 强调色
    
    # 动画配置
    animations = Column(JSON)  # 动画配置：{"fan_rotation": true, "led_blink": true, "status_indicator": true}
    
    # 状态可视化映射
    status_mapping = Column(JSON)  # 状态到颜色/动画的映射
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    device = relationship("Device", back_populates="digital_twin_config")

class DigitalTwinScene(Base):
    """数字孪生场景配置表"""
    __tablename__ = "digital_twin_scenes"
    
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    
    # 场景配置
    scene_config = Column(JSON, nullable=False)  # 完整场景配置
    
    # 默认值配置
    default_values = {
        "name": "default",
        "scene_config": {
            "camera": {
                "position": [0, 10, 15],
                "fov": 50,
                "near": 0.1,
                "far": 1000
            },
            "lights": [
                {
                    "type": "ambient",
                    "color": "#ffffff",
                    "intensity": 0.5
                },
                {
                    "type": "directional",
                    "position": [5, 10, 5],
                    "color": "#ffffff",
                    "intensity": 0.8
                }
            ],
            "grid": {
                "enabled": True,
                "size": 50,
                "divisions": 50,
                "colorCenterLine": "#666666",
                "colorGrid": "#444444"
            },
            "axes": {
                "enabled": True,
                "size": 5
            },
            "ground": {
                "enabled": True,
                "color": "#333333",
                "opacity": 0.8
            }
        }
    }
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    station = relationship("Station")

class DigitalTwinDataPoint(Base):
    """数字孪生数据映射点 - 设备参数到3D可视化属性的映射"""
    __tablename__ = "digital_twin_data_points"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    
    # 数据点配置
    param_key = Column(String(100), nullable=False)        # 遥测参数键（如 voltage, current, power）
    display_name = Column(String(100), nullable=False)     # 显示名称
    unit = Column(String(20), default="")                  # 单位
    
    # 可视化映射
    visual_type = Column(String(30), default="color")      # 映射类型: color/scale/position/animation/text
    normal_range = Column(JSON)                              # 正常范围: {"min": 0, "max": 100}
    warn_range = Column(JSON)                                # 告警范围: {"min": 100, "max": 200}
    danger_range = Column(JSON)                              # 危险范围: {"min": 200, "max": 300}
    
    # 颜色映射
    normal_color = Column(String(20), default="#52c41a")    # 正常颜色
    warn_color = Column(String(20), default="#faad14")      # 告警颜色
    danger_color = Column(String(20), default="#ff4d4f")    # 危险颜色
    
    # 动画映射
    animation_config = Column(JSON)                          # 动画配置
    
    # 数值显示
    show_value = Column(Boolean, default=True)              # 是否显示数值
    show_unit = Column(Boolean, default=True)               # 是否显示单位
    decimal_places = Column(Integer, default=1)             # 小数位数
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    device = relationship("Device")

# 在Device模型中添加关系
# 需要修改原有的Device模型，添加：
# digital_twin_config = relationship("DigitalTwinModel", back_populates="device", uselist=False)