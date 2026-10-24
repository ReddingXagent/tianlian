/**
 * 天链 V3 - Dashboard 常量与兜底数据
 */

// 7天告警趋势兜底数据 —— 仅当 /reports/alarms 不可用时使用（确定性占位，非随机）
export const FALLBACK_ALARM_TREND_COUNTS = [3, 5, 2, 7, 4, 6, 3];

export const buildFallbackAlarmTrend = (): Array<{ date: string; count: number }> => {
  const trend: Array<{ date: string; count: number }> = [];
  for (let i = 6; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    trend.push({
      date: date.toISOString().slice(0, 10),
      count: FALLBACK_ALARM_TREND_COUNTS[6 - i],
    });
  }
  return trend;
};
