import { RevenueRecord, RevenueSummary } from '../types';

export type RevenuePeriod = 'day' | 'week' | 'month';

// CSV 字段转义：含逗号/引号/换行时用双引号包裹并转义内部引号
export const escapeCsv = (value: string | number): string => {
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export interface BuildCsvOptions {
  // 固定生成时间，便于测试；缺省取当前时间
  generatedAt?: string;
}

/**
 * 将营收记录汇总为 CSV 字符串（含汇总区 + 明细区 + 合计行）。
 * 纯函数，不依赖 RN 运行时，方便单元测试。
 */
export const buildRevenueCsv = (
  records: RevenueRecord[],
  summary: RevenueSummary,
  period: RevenuePeriod,
  options: BuildCsvOptions = {}
): string => {
  const periodLabel = period === 'day' ? '日' : period === 'week' ? '周' : '月';
  const generatedAt = options.generatedAt ?? new Date().toISOString();

  const lines: string[] = [];
  lines.push('天链V3 营收统计');
  lines.push(`周期,${escapeCsv(periodLabel)}`);
  lines.push(`生成时间,${escapeCsv(generatedAt)}`);
  lines.push('');
  lines.push('汇总');
  lines.push(`今日,${escapeCsv(summary.today.toFixed(2))}`);
  lines.push(`本周,${escapeCsv(summary.week.toFixed(2))}`);
  lines.push(`本月,${escapeCsv(summary.month.toFixed(2))}`);
  lines.push(`累计,${escapeCsv(summary.total.toFixed(2))}`);
  lines.push('');
  lines.push('明细');
  lines.push('日期,营收金额(元),订单数');
  for (const r of records) {
    lines.push(
      `${escapeCsv(r.date)},${escapeCsv(r.amount.toFixed(2))},${escapeCsv(r.orderCount)}`
    );
  }

  const totalAmount = records.reduce((sum, r) => sum + r.amount, 0);
  const totalOrders = records.reduce((sum, r) => sum + r.orderCount, 0);
  lines.push(`合计,${escapeCsv(totalAmount.toFixed(2))},${escapeCsv(totalOrders)}`);

  return lines.join('\n');
};

// 生成导出文件名
export const revenueCsvFilename = (period: RevenuePeriod): string => {
  const prefix = period === 'day' ? 'daily' : period === 'week' ? 'weekly' : 'monthly';
  return `tianlian-revenue-${prefix}.csv`;
};
