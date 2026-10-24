"""
天链 V2 Phase1 - 遥测数据专表拆分模型
拆分72列宽表为三张专表，提升IO效率和查询性能
"""
from sqlalchemy import Column, BigInteger, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional

from app.core.database import Base


# ========== 设备类型映射 ==========
# 用于API层路由判断
DEVICE_TYPE_TABLE_MAP = {
    "pv_inverter": "TelemetryPV",       # 光伏逆变器 -> PV表
    "battery_inverter": "TelemetryBattery",  # 储能逆变器 -> Battery表
    "pcs": "TelemetryBattery",          # PCS -> Battery表
    "battery": "TelemetryBattery",      # 储能电池柜 -> Battery表
    "charger_dc": "TelemetryCharger",    # 直流充电桩 -> Charger表
    "charger_ac": "TelemetryCharger",    # 交流充电桩 -> Charger表
}


class TelemetryPV(Base):
    """光伏逆变器遥测数据专表 (~25列)
    
    仅存储光伏逆变器相关数据，减少冗余字段
    新增: station_id, region_id, pod_id 用于多Pod矩阵架构
    """
    __tablename__ = "telemetry_pv"
    
    # ========== 主键与关联 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # ========== 区域路由字段（新增）==========
    region_id = Column(String(32), default="default", nullable=False, index=True)  # 区域标识
    pod_id = Column(String(32), default="pod-01", nullable=False, index=True)      # Pod标识
    
    # ========== 电网侧数据 ==========
    grid_voltage_a = Column(Float)  # A相电压 V
    grid_voltage_b = Column(Float)  # B相电压 V
    grid_voltage_c = Column(Float)  # C相电压 V
    grid_current_a = Column(Float)  # A相电流 A
    grid_current_b = Column(Float)  # B相电流 A
    grid_current_c = Column(Float)  # C相电流 A
    grid_power_total = Column(Float)  # 总有功功率 kW
    grid_frequency = Column(Float)    # 电网频率 Hz
    grid_power_factor = Column(Float) # 功率因数
    
    # ========== 光伏侧数据 ==========
    pv1_voltage = Column(Float)   # PV1电压 V
    pv1_current = Column(Float)   # PV1电流 A
    pv1_power = Column(Float)     # PV1功率 kW
    pv2_voltage = Column(Float)   # PV2电压 V
    pv2_current = Column(Float)   # PV2电流 A
    pv2_power = Column(Float)     # PV2功率 kW
    pv_power_total = Column(Float)  # 光伏总功率 kW
    bus_voltage_pos = Column(Float)  # BUS+母线电压
    bus_voltage_neg = Column(Float)  # BUS-母线电压
    
    # ========== 温度数据 ==========
    internal_temperature = Column(Float)  # 机内温度 ℃
    pv_temperature = Column(Float)        # PV温度 ℃
    inv_temperature = Column(Float)       # 逆变温度 ℃
    battery_temperature = Column(Float)   # 电池温度 ℃
    
    # ========== 电能数据 ==========
    daily_generation = Column(Float)   # 今日发电量 kWh
    total_generation = Column(Float)   # 累积发电量 kWh
    
    # ========== 运行状态 ==========
    run_time = Column(Integer)      # 运行时间 分钟
    run_mode = Column(Integer)      # 运行模式
    system_status = Column(Integer) # 系统状态字
    
    # ========== 复合索引 ==========
    __table_args__ = (
        Index('idx_pv_station_device_ts', 'station_id', 'device_id', timestamp.desc()),
        Index('idx_pv_device_region', 'device_id', 'region_id'),
        Index('idx_pv_ts', timestamp.desc()),
    )
    
    # 关系
    device = relationship("Device", back_populates="telemetry_pv_records")
    station = relationship("Station", back_populates="telemetry_pv_records")


class TelemetryBattery(Base):
    """储能电池/PCS遥测数据专表 (~30列)
    
    仅存储储能相关数据
    新增: station_id, region_id, pod_id 用于多Pod矩阵架构
    """
    __tablename__ = "telemetry_battery"
    
    # ========== 主键与关联 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # ========== 区域路由字段（新增）==========
    region_id = Column(String(32), default="default", nullable=False, index=True)
    pod_id = Column(String(32), default="pod-01", nullable=False, index=True)
    
    # ========== 电网侧数据（PCS）==========
    grid_voltage_a = Column(Float)
    grid_voltage_b = Column(Float)
    grid_voltage_c = Column(Float)
    grid_current_a = Column(Float)
    grid_current_b = Column(Float)
    grid_current_c = Column(Float)
    grid_power_total = Column(Float)
    grid_frequency = Column(Float)
    grid_power_factor = Column(Float)
    
    # ========== 电池侧数据 ==========
    battery_voltage = Column(Float)  # 电池电压 V
    battery_current = Column(Float)  # 电池电流 A（正=充电，负=放电）
    battery_power = Column(Float)    # 电池功率 kW
    battery_soc = Column(Float)      # 电池SOC %
    battery_soh = Column(Float)      # 电池SOH %
    battery_temperature = Column(Float)  # 电池温度 ℃
    
    # ========== BMS数据 ==========
    bms_charge_current_limit = Column(Float)    # BMS充电电流限值
    bms_discharge_current_limit = Column(Float) # BMS放电电流限值
    bms_alarm_word = Column(Integer)   # BMS告警字1
    bms_alarm_word2 = Column(Integer)  # BMS告警字2
    bms_alarm_word3 = Column(Integer)  # BMS告警字3
    
    # ========== 电能数据 ==========
    daily_charge = Column(Float)     # 今日充电量 kWh
    daily_discharge = Column(Float)  # 今日放电量 kWh
    total_charge = Column(Float)     # 累积充电量 kWh
    total_discharge = Column(Float)  # 累积放电量 kWh
    
    # ========== 温度数据 ==========
    internal_temperature = Column(Float)   # 机内温度 ℃
    ambient_temperature = Column(Float)    # 环境温度 ℃
    
    # ========== 运行状态 ==========
    run_time = Column(Integer)
    run_mode = Column(Integer)
    system_status = Column(Integer)
    
    # ========== 复合索引 ==========
    __table_args__ = (
        Index('idx_battery_station_device_ts', 'station_id', 'device_id', timestamp.desc()),
        Index('idx_battery_device_region', 'device_id', 'region_id'),
        Index('idx_battery_ts', timestamp.desc()),
    )
    
    # 关系
    device = relationship("Device", back_populates="telemetry_battery_records")
    station = relationship("Station", back_populates="telemetry_battery_records")


class TelemetryCharger(Base):
    """充电桩遥测数据专表 (~18列)
    
    仅存储充电桩相关数据
    新增: station_id, region_id, pod_id 用于多Pod矩阵架构
    """
    __tablename__ = "telemetry_charger"
    
    # ========== 主键与关联 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, index=True)  # Phase1: FK类型统一为BigInt
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # ========== 区域路由字段（新增）==========
    region_id = Column(String(32), default="default", nullable=False, index=True)
    pod_id = Column(String(32), default="pod-01", nullable=False, index=True)
    
    # ========== 充电桩输出数据 ==========
    charger_voltage = Column(Float)   # 输出电压 V
    charger_current = Column(Float)   # 输出电流 A
    charger_power = Column(Float)     # 输出功率 kW
    charger_soc = Column(Float)       # 车辆SOC %
    charger_kwh = Column(Float)       # 已充电量 kWh
    
    # ========== 充电枪状态 ==========
    gun_status = Column(Integer)       # 充电枪状态（0=空闲,1=充电中,2=已完成）
    gun_temperature = Column(Float)    # 充电枪温度 ℃
    
    # ========== 温度数据 ==========
    internal_temperature = Column(Float)   # 机内温度 ℃
    ambient_temperature = Column(Float)    # 环境温度 ℃
    
    # ========== 运行状态 ==========
    run_time = Column(Integer)
    run_mode = Column(Integer)
    system_status = Column(Integer)
    
    # ========== 复合索引 ==========
    __table_args__ = (
        Index('idx_charger_station_device_ts', 'station_id', 'device_id', timestamp.desc()),
        Index('idx_charger_device_region', 'device_id', 'region_id'),
        Index('idx_charger_ts', timestamp.desc()),
    )
    
    # 关系
    device = relationship("Device", back_populates="telemetry_charger_records")
    station = relationship("Station", back_populates="telemetry_charger_records")


# ========== 遥测数据类型枚举 ==========
class TelemetryTableType:
    """遥测表类型常量"""
    PV = "pv"
    BATTERY = "battery"
    CHARGER = "charger"
    LEGACY = "legacy"  # 向后兼容旧表


def get_telemetry_model_by_device_type(device_type: str) -> Optional[type]:
    """根据设备类型返回对应的遥测模型类
    
    Args:
        device_type: 设备类型字符串 (DeviceType enum value)
        
    Returns:
        对应的模型类: TelemetryPV, TelemetryBattery, TelemetryCharger
        如果设备类型不匹配，返回 None (使用旧 Telemetry 表)
    """
    table_name = DEVICE_TYPE_TABLE_MAP.get(device_type)
    if table_name == "TelemetryPV":
        return TelemetryPV
    elif table_name == "TelemetryBattery":
        return TelemetryBattery
    elif table_name == "TelemetryCharger":
        return TelemetryCharger
    return None