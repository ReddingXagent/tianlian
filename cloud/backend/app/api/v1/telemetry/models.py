"""
遥测数据上报 Pydantic 模型

原 app/api/v1/telemetry.py(1105行) 按职责拆分而来(卡 61109a8a)。
定义设备遥测上报的请求体模型(光伏/储能/充电桩/旧版兼容/批量), 无业务逻辑。
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class TelemetryReportBase(BaseModel):
    """遥测数据上报基类"""
    device_id: int
    region_id: Optional[str] = Field(default="default", description="区域标识")
    pod_id: Optional[str] = Field(default="pod-01", description="Pod标识")


class TelemetryPVReport(TelemetryReportBase):
    """光伏逆变器遥测上报"""
    # 电网侧
    grid_voltage_a: Optional[float] = None
    grid_voltage_b: Optional[float] = None
    grid_voltage_c: Optional[float] = None
    grid_current_a: Optional[float] = None
    grid_current_b: Optional[float] = None
    grid_current_c: Optional[float] = None
    grid_power_total: Optional[float] = None
    grid_frequency: Optional[float] = None
    grid_power_factor: Optional[float] = None

    # 光伏侧
    pv1_voltage: Optional[float] = None
    pv1_current: Optional[float] = None
    pv1_power: Optional[float] = None
    pv2_voltage: Optional[float] = None
    pv2_current: Optional[float] = None
    pv2_power: Optional[float] = None
    pv_power_total: Optional[float] = None
    bus_voltage_pos: Optional[float] = None
    bus_voltage_neg: Optional[float] = None

    # 温度
    internal_temperature: Optional[float] = None
    pv_temperature: Optional[float] = None
    inv_temperature: Optional[float] = None

    # 电能
    daily_generation: Optional[float] = None
    total_generation: Optional[float] = None

    # 运行状态
    run_time: Optional[int] = None
    run_mode: Optional[int] = None
    system_status: Optional[int] = None


class TelemetryBatteryReport(TelemetryReportBase):
    """储能电池/PCS遥测上报"""
    # 电网侧
    grid_voltage_a: Optional[float] = None
    grid_voltage_b: Optional[float] = None
    grid_voltage_c: Optional[float] = None
    grid_current_a: Optional[float] = None
    grid_current_b: Optional[float] = None
    grid_current_c: Optional[float] = None
    grid_power_total: Optional[float] = None
    grid_frequency: Optional[float] = None
    grid_power_factor: Optional[float] = None

    # 电池侧
    battery_voltage: Optional[float] = None
    battery_current: Optional[float] = None
    battery_power: Optional[float] = None
    battery_soc: Optional[float] = None
    battery_soh: Optional[float] = None
    battery_temperature: Optional[float] = None

    # BMS
    bms_charge_current_limit: Optional[float] = None
    bms_discharge_current_limit: Optional[float] = None
    bms_alarm_word: Optional[int] = None
    bms_alarm_word2: Optional[int] = None
    bms_alarm_word3: Optional[int] = None

    # 电能
    daily_charge: Optional[float] = None
    daily_discharge: Optional[float] = None
    total_charge: Optional[float] = None
    total_discharge: Optional[float] = None

    # 温度
    internal_temperature: Optional[float] = None
    ambient_temperature: Optional[float] = None

    # 运行状态
    run_time: Optional[int] = None
    run_mode: Optional[int] = None
    system_status: Optional[int] = None


class TelemetryChargerReport(TelemetryReportBase):
    """充电桩遥测上报"""
    charger_voltage: Optional[float] = None
    charger_current: Optional[float] = None
    charger_power: Optional[float] = None
    charger_soc: Optional[float] = None
    charger_kwh: Optional[float] = None
    gun_status: Optional[int] = None
    gun_temperature: Optional[float] = None
    internal_temperature: Optional[float] = None
    ambient_temperature: Optional[float] = None
    run_time: Optional[int] = None
    run_mode: Optional[int] = None
    system_status: Optional[int] = None


class TelemetryReportLegacy(BaseModel):
    """旧版遥测数据上报模型(向后兼容)"""
    device_id: int

    # 电网侧数据
    grid_voltage_a: Optional[float] = None
    grid_current_a: Optional[float] = None
    grid_power_a: Optional[float] = None
    grid_reactive_a: Optional[float] = None
    grid_voltage_b: Optional[float] = None
    grid_current_b: Optional[float] = None
    grid_power_b: Optional[float] = None
    grid_reactive_b: Optional[float] = None
    grid_voltage_c: Optional[float] = None
    grid_current_c: Optional[float] = None
    grid_power_c: Optional[float] = None
    grid_reactive_c: Optional[float] = None
    grid_frequency: Optional[float] = None
    grid_power_total: Optional[float] = None
    grid_reactive_total: Optional[float] = None
    grid_power_factor: Optional[float] = None

    # 电池侧数据
    battery_voltage: Optional[float] = None
    battery_current: Optional[float] = None
    battery_power: Optional[float] = None
    battery_soc: Optional[float] = None
    battery_soh: Optional[float] = None
    battery_temperature: Optional[float] = None

    # 光伏侧数据
    pv1_voltage: Optional[float] = None
    pv1_current: Optional[float] = None
    pv1_power: Optional[float] = None
    pv2_voltage: Optional[float] = None
    pv2_current: Optional[float] = None
    pv2_power: Optional[float] = None
    pv_power_total: Optional[float] = None

    # 充电桩数据
    charger_voltage: Optional[float] = None
    charger_current: Optional[float] = None
    charger_power: Optional[float] = None
    charger_soc: Optional[float] = None
    charger_kwh: Optional[float] = None
    gun_status: Optional[int] = None
    gun_temperature: Optional[float] = None

    # 温度数据
    ambient_temperature: Optional[float] = None
    internal_temperature: Optional[float] = None

    # 电能数据
    daily_generation: Optional[float] = None
    daily_charge: Optional[float] = None
    daily_discharge: Optional[float] = None
    total_generation: Optional[float] = None
    total_charge: Optional[float] = None
    total_discharge: Optional[float] = None

    # 运行状态
    run_time: Optional[int] = None
    run_mode: Optional[int] = None
    system_status: Optional[int] = None


class TelemetryBatchReport(BaseModel):
    """批量遥测数据上报"""
    records: List[TelemetryReportLegacy] = Field(..., description="遥测数据列表")
    region_id: Optional[str] = Field(default="default", description="区域标识")
    pod_id: Optional[str] = Field(default="pod-01", description="Pod标识")
