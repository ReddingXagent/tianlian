/**
 * 遥测页面常量：确定性兜底基线
 */

// ═══ 确定性兜底（无 Math.random）═══
// 后端实测契约（见 analytics-dashboard-panel-api-contract 记忆）：
// - telemetry history 只返回 {count,mode}，不返回数据点 → 走确定性时序兜底
// - latest 仅 grid_power_total/battery_soc/charger_power 等少量字段
// - stats 有 grid.avg_voltage_a/avg_power、thermal.avg_temp 等聚合均值
// 缺失字段用以下真实物理典型值兜底，保证相同入参恒等输出（非随机）。
export const FALLBACK_BASELINE = {
  grid_voltage: 220,
  grid_frequency: 50,
  grid_power: 5,
  grid_power_factor: 0.95,
  battery_voltage: 400,
  battery_current: 0,
  battery_power: 0,
  battery_soc: 50,
  battery_soh: 95,
  battery_temperature: 28,
  pv1_voltage: 400,
  pv1_current: 5,
  pv1_power: 2,
  pv_power_total: 4,
  charger_voltage: 400,
  charger_current: 0,
  charger_power: 0,
  charger_soc: 50,
  gun_status: 0, // 0=空闲, 1=充电, 2=故障
  gun_temperature: 35,
  internal_temperature: 40,
  ambient_temperature: 25,
};
export type Baselines = typeof FALLBACK_BASELINE;

// 确定性历史时序点数
export const HISTORY_POINTS = 24;
