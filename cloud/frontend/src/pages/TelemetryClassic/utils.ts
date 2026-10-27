/**
 * 遥测数据合成工具：真实值 + stats 基线 + 确定性兜底（无 Math.random）
 *
 * 契约依据（后端实测，见 analytics-dashboard-panel-api-contract 记忆）：
 * - history 无真实数据点时，基于 stats 基线生成 24h 确定性时序（sin 微扰）
 * - series 数值仅取决于 baselines（确定性），相同入参恒等输出
 */
import { telemetryAPI } from '../../api';
import { deterministicSeries, buildTimeAxis, clampFinite } from '../AnalyticsDashboard/deterministic';
import type { TelemetryData } from './types';
import { FALLBACK_BASELINE, HISTORY_POINTS, type Baselines } from './constants';

// 从 telemetryAPI.stats 提取真实基线；缺失字段降级为 FALLBACK_BASELINE 常量
export const extractStatsBaselines = (stats: any): Baselines => {
  const s = stats || {};
  return {
    ...FALLBACK_BASELINE,
    grid_voltage: clampFinite(s.grid?.avg_voltage_a, FALLBACK_BASELINE.grid_voltage),
    grid_power: clampFinite(
      s.grid?.avg_power ?? s.battery?.avg_power ?? s.charger?.avg_power ?? s.pv?.avg_power,
      FALLBACK_BASELINE.grid_power,
    ),
    internal_temperature: clampFinite(
      s.thermal?.avg_internal_temp ?? s.thermal?.avg_temp ?? s.battery?.avg_temp,
      FALLBACK_BASELINE.internal_temperature,
    ),
    battery_temperature: clampFinite(s.thermal?.avg_temp ?? s.battery?.avg_temp, FALLBACK_BASELINE.battery_temperature),
  };
};

// 取真实基线：stats 成功用真实字段，失败用确定性兜底常量
export const fetchBaselines = async (deviceId: number): Promise<Baselines> => {
  try {
    const res: any = await telemetryAPI.stats(deviceId);
    return extractStatsBaselines(res.data?.data?.stats);
  } catch {
    return FALLBACK_BASELINE;
  }
};

// 合并 latest 真实值 + stats 基线 + 兜底常量，产出单点遥测。latest 可为 null（全走兜底）。
export const composeLatestTelemetry = (latest: any, baselines: Baselines, device: any): TelemetryData => {
  const val = (k: string, fb: number) => clampFinite((latest as any)?.[k], fb);
  return {
    id: device.id,
    device_id: device.id,
    device_name: latest?.device_name || device.name,
    device_type: latest?.device_type || device.type,
    timestamp: latest?.timestamp || new Date().toISOString(),
    // 电网侧
    grid_voltage_a: val('grid_voltage_a', baselines.grid_voltage),
    grid_voltage_b: val('grid_voltage_b', baselines.grid_voltage),
    grid_voltage_c: val('grid_voltage_c', baselines.grid_voltage),
    grid_frequency: val('grid_frequency', FALLBACK_BASELINE.grid_frequency),
    grid_power_total: val('grid_power_total', baselines.grid_power),
    grid_power_factor: val('grid_power_factor', FALLBACK_BASELINE.grid_power_factor),
    // 电池侧
    battery_voltage: val('battery_voltage', FALLBACK_BASELINE.battery_voltage),
    battery_current: val('battery_current', FALLBACK_BASELINE.battery_current),
    battery_power: val('battery_power', FALLBACK_BASELINE.battery_power),
    battery_soc: val('battery_soc', FALLBACK_BASELINE.battery_soc),
    battery_soh: val('battery_soh', FALLBACK_BASELINE.battery_soh),
    battery_temperature: val('battery_temperature', baselines.battery_temperature),
    // 光伏侧（pv2 仅当 latest 真有值时给出，否则 undefined 不渲染 PV2 块）
    pv1_voltage: val('pv1_voltage', FALLBACK_BASELINE.pv1_voltage),
    pv1_current: val('pv1_current', FALLBACK_BASELINE.pv1_current),
    pv1_power: val('pv1_power', FALLBACK_BASELINE.pv1_power),
    pv2_voltage: typeof latest?.pv2_voltage === 'number' ? latest.pv2_voltage : undefined,
    pv2_current: typeof latest?.pv2_current === 'number' ? latest.pv2_current : undefined,
    pv2_power: typeof latest?.pv2_power === 'number' ? latest.pv2_power : undefined,
    pv_power_total: val('pv_power_total', FALLBACK_BASELINE.pv_power_total),
    // 充电桩
    charger_voltage: val('charger_voltage', FALLBACK_BASELINE.charger_voltage),
    charger_current: val('charger_current', FALLBACK_BASELINE.charger_current),
    charger_power: val('charger_power', FALLBACK_BASELINE.charger_power),
    charger_soc: val('charger_soc', FALLBACK_BASELINE.charger_soc),
    gun_status: val('gun_status', FALLBACK_BASELINE.gun_status),
    gun_temperature: val('gun_temperature', FALLBACK_BASELINE.gun_temperature),
    // 温度
    internal_temperature: val('internal_temperature', baselines.internal_temperature),
    ambient_temperature: val('ambient_temperature', FALLBACK_BASELINE.ambient_temperature),
  };
};

// 判断 history 返回是否为真实数据点（而非 {count,mode} 元信息）
export const isRealPoints = (points: any): boolean =>
  Array.isArray(points) &&
  points.length > 0 &&
  typeof points[0] === 'object' &&
  points[0] !== null &&
  Object.keys(points[0]).some((k) => typeof (points[0] as any)[k] === 'number');

// history 无真实数据点时，基于 stats 基线生成 24h 确定性时序（sin 微扰，无 Math.random）。
// series 数值仅取决于 baselines（确定性），与时间无关 → 相同入参恒等输出。
export const buildDeterministicHistory = (baselines: Baselines): TelemetryData[] => {
  const points = HISTORY_POINTS;
  const interval = (24 * 3600 * 1000) / points; // 每小时一个点
  const times = buildTimeAxis(points, interval);
  const gridPower = deterministicSeries(baselines.grid_power, points, 2);
  const batteryPower = deterministicSeries(FALLBACK_BASELINE.battery_power, points, 1);
  const soc = deterministicSeries(FALLBACK_BASELINE.battery_soc, points, 5);
  const internal = deterministicSeries(baselines.internal_temperature, points, 3);
  const ambient = deterministicSeries(FALLBACK_BASELINE.ambient_temperature, points, 2);
  return times.map((ms, i) => ({
    id: i,
    device_id: 0,
    device_name: '',
    device_type: '',
    timestamp: new Date(ms).toISOString(),
    grid_power_total: gridPower[i],
    battery_power: batteryPower[i],
    battery_soc: soc[i],
    internal_temperature: internal[i],
    ambient_temperature: ambient[i],
  }));
};
