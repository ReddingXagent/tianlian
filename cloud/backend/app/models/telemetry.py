"""
遥测数据模型 - 基于光储充设备协议分析
"""
from typing import Any, Dict

from sqlalchemy import Column, Integer, BigInteger, DateTime, ForeignKey, Float, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

class Telemetry(Base):
    """设备遥测数据表 - @deprecated 向后兼容
    
    Phase1 改造后，请根据设备类型使用专表：
    - pv_inverter -> TelemetryPV
    - battery_inverter/pcs/battery -> TelemetryBattery
    - charger_dc/charger_ac -> TelemetryCharger
    
    此表仅作为向后兼容保留，新数据应写入专表。
    """
    __tablename__ = "telemetry"
    # 复合索引: 逐设备时间窗查询 (analytics_tasks/maintenance_tasks 避免单列索引回表再过滤)
    __table_args__ = (
        Index("ix_telemetry_device_ts", "device_id", "timestamp"),
    )

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # ========== 电网侧数据（逆变器/PCS）==========
    # A相
    grid_voltage_a = Column(Float)  # A相电压 V
    grid_current_a = Column(Float)  # A相电流 A
    grid_power_a = Column(Float)  # A相有功功率 kW
    grid_reactive_a = Column(Float)  # A相无功功率 kVar
    
    # B相
    grid_voltage_b = Column(Float)
    grid_current_b = Column(Float)
    grid_power_b = Column(Float)
    grid_reactive_b = Column(Float)
    
    # C相
    grid_voltage_c = Column(Float)
    grid_current_c = Column(Float)
    grid_power_c = Column(Float)
    grid_reactive_c = Column(Float)
    
    # 总量
    grid_frequency = Column(Float)  # 电网频率 Hz
    grid_power_total = Column(Float)  # 总有功功率 kW
    grid_reactive_total = Column(Float)  # 总无功功率 kVar
    grid_power_factor = Column(Float)  # 功率因数
    
    # ========== 逆变输出数据（逆变器）==========
    inv_voltage_a = Column(Float)  # 逆变A相电压
    inv_current_a = Column(Float)  # 逆变A相电流
    inv_power_a = Column(Float)  # 逆变A相功率
    
    inv_voltage_b = Column(Float)
    inv_current_b = Column(Float)
    inv_power_b = Column(Float)
    
    inv_voltage_c = Column(Float)
    inv_current_c = Column(Float)
    inv_power_c = Column(Float)
    
    inv_power_total = Column(Float)  # 逆变总功率 kW
    
    # ========== 电池侧数据（储能逆变器/PCS）==========
    battery_voltage = Column(Float)  # 电池电压 V
    battery_current = Column(Float)  # 电池电流 A（正=充电，负=放电）
    battery_power = Column(Float)  # 电池功率 kW
    battery_soc = Column(Float)  # 电池SOC %
    battery_soh = Column(Float)  # 电池SOH %
    battery_temperature = Column(Float)  # 电池温度 ℃
    
    # BMS数据
    bms_charge_current_limit = Column(Float)  # BMS充电电流限值
    bms_discharge_current_limit = Column(Float)  # BMS放电电流限值
    bms_alarm_word = Column(Integer)  # BMS告警字1
    bms_alarm_word2 = Column(Integer)  # BMS告警字2
    bms_alarm_word3 = Column(Integer)  # BMS告警字3
    
    # ========== 光伏侧数据（光伏逆变器）==========
    pv1_voltage = Column(Float)  # PV1电压 V
    pv1_current = Column(Float)  # PV1电流 A
    pv1_power = Column(Float)  # PV1功率 kW
    
    pv2_voltage = Column(Float)  # PV2电压
    pv2_current = Column(Float)
    pv2_power = Column(Float)
    
    pv_power_total = Column(Float)  # 光伏总功率 kW
    bus_voltage_pos = Column(Float)  # BUS+母线电压
    bus_voltage_neg = Column(Float)  # BUS-母线电压
    
    # ========== 充电桩数据（充电桩）==========
    charger_voltage = Column(Float)  # 输出电压 V
    charger_current = Column(Float)  # 输出电流 A
    charger_power = Column(Float)  # 输出功率 kW
    charger_soc = Column(Float)  # 车辆SOC %
    charger_kwh = Column(Float)  # 已充电量 kWh
    
    gun_status = Column(Integer)  # 充电枪状态（0=空闲,1=充电中,2=已完成）
    gun_temperature = Column(Float)  # 充电枪温度 ℃
    
    # ========== 温度数据（通用）==========
    ambient_temperature = Column(Float)  # 环境温度 ℃
    internal_temperature = Column(Float)  # 机内温度 ℃
    pv_temperature = Column(Float)  # PV温度 ℃
    inv_temperature = Column(Float)  # 逆变温度 ℃
    
    # ========== 电能数据（通用）==========
    daily_generation = Column(Float)  # 今日发电量 kWh
    daily_consumption = Column(Float)  # 今日用电量 kWh
    daily_charge = Column(Float)  # 今日充电量 kWh
    daily_discharge = Column(Float)  # 今日放电量 kWh
    
    total_generation = Column(Float)  # 累积发电量 kWh
    total_consumption = Column(Float)  # 累积用电量 kWh
    total_charge = Column(Float)  # 累积充电量 kWh
    total_discharge = Column(Float)  # 累积放电量 kWh
    
    # ========== 运行状态（通用）==========
    run_time = Column(Integer)  # 运行时间 分钟
    run_mode = Column(Integer)  # 运行模式（电池优先/负载优先/电网优先等）
    system_status = Column(Integer)  # 系统状态字
    
    # 关系
    device = relationship("Device", back_populates="telemetry_records")

    @property
    def data(self) -> Dict[str, Any]:
        """扁平列度量聚合为字典（兼容 record.data 访问路径）。

        Telemetry 为扁平列模型，无独立 JSON ``data`` 列；而服务层
        ``get_history_data`` / ``get_statistics`` 通过 ``record.data`` 取值。
        此 property 遍历所有 Column，排除主键/外键/时间列
        （id / device_id / timestamp），只返回非 None 的度量字段。
        """
        excluded = {"id", "device_id", "timestamp"}
        return {
            col.name: getattr(self, col.name)
            for col in self.__table__.columns
            if col.name not in excluded and getattr(self, col.name) is not None
        }

# Device模型添加telemetry关系（在models/device.py中添加）
# telemetry_records = relationship("Telemetry", back_populates="device", cascade="all, delete-orphan")