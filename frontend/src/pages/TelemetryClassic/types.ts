/**
 * 遥测数据类型定义
 *
 * 光储充设备遥测数据契约（电网侧 / 电池侧 / 光伏侧 / 充电桩 / 温度）
 */
export interface TelemetryData {
  id: number;
  device_id: number;
  device_name: string;
  device_type: string;
  timestamp: string;

  // 电网侧
  grid_voltage_a?: number;
  grid_voltage_b?: number;
  grid_voltage_c?: number;
  grid_current_a?: number;
  grid_power_a?: number;
  grid_power_total?: number;
  grid_frequency?: number;
  grid_power_factor?: number;

  // 电池侧
  battery_voltage?: number;
  battery_current?: number;
  battery_power?: number;
  battery_soc?: number;
  battery_soh?: number;
  battery_temperature?: number;

  // 光伏侧
  pv1_voltage?: number;
  pv1_current?: number;
  pv1_power?: number;
  pv2_voltage?: number;
  pv2_current?: number;
  pv2_power?: number;
  pv_power_total?: number;

  // 充电桩
  charger_voltage?: number;
  charger_current?: number;
  charger_power?: number;
  charger_soc?: number;
  gun_status?: number;
  gun_temperature?: number;

  // 温度
  internal_temperature?: number;
  ambient_temperature?: number;
}
