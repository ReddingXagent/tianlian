/**
 * 确定性兜底工具（无 Math.random）
 *
 * 用途：AnalyticsDashboard 子组件在后端字段缺失或 API 失败时，
 * 基于真实基线生成 sin 确定性序列/数值，保证两次渲染恒等、图表不空。
 * 契约依据：telemetry history 不返回数据点，stats 无电流字段，latest 无温度/电压。
 */

/** 基于真实基线的确定性 sin 微扰序列（n 个点，振幅 amp）。不含 Math.random。 */
export const deterministicSeries = (base: number, n: number, amp: number): number[] => {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    out.push(+(base + amp * Math.sin(i)).toFixed(2));
  }
  return out;
};

/** 单个确定性数值：base + amp*sin(t)。给定相同 (base,t) 恒等输出。t 通常为秒级时间戳。 */
export const deterministicValue = (base: number, t: number, amp: number): number =>
  +(base + amp * Math.sin(t)).toFixed(2);

/**
 * 确定性时间轴：从 (anchor - points*interval) 到 anchor，等间隔 points 个点。
 * anchor 缺省取 Date.now()；测试可注入固定锚点。
 */
export const buildTimeAxis = (points: number, intervalMs: number, anchorMs?: number): number[] => {
  const anchor = anchorMs ?? Date.now();
  const out: number[] = [];
  for (let i = 0; i < points; i++) {
    out.push(anchor - (points - 1 - i) * intervalMs);
  }
  return out;
};

/** 非有限数值（NaN/Infinity/null/undefined）降级为 fallback。 */
export const clampFinite = (v: number | null | undefined, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : fallback;
