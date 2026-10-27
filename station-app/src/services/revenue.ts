import { ApiResponse, RevenueRecord, RevenueQuery } from '../types';
import api from './client';
import { Raw, num, str } from './mappers';

// =====================
// 营收 API (闭环战役A3 经营域: /business/*, 云端待部署)
// =====================
export const revenueApi = {
  // 汇总: 今日/本周/本月/累计 = 全量 + daily(30天) 客户端聚合
  async getSummary(): Promise<ApiResponse<{ today: number; week: number; month: number; total: number }>> {
    const [totalRes, dailyRes] = await Promise.all([
      api.get('/business/revenue/summary'),
      api.get('/business/revenue/daily', { params: { days: 30 } }),
    ]);
    const total = totalRes.data?.data?.net_revenue ?? 0;
    const daily: { date: string; net_revenue: number }[] = dailyRes.data?.data ?? [];
    const month = daily.reduce((s, d) => s + (d.net_revenue || 0), 0);
    const week = daily.slice(-7).reduce((s, d) => s + (d.net_revenue || 0), 0);
    const today = daily.length > 0 ? daily[daily.length - 1]!.net_revenue || 0 : 0;
    return {
      code: 200,
      message: 'success',
      data: {
        today: Math.round(today * 100) / 100,
        week: Math.round(week * 100) / 100,
        month: Math.round(month * 100) / 100,
        total: Math.round(total * 100) / 100,
      },
    };
  },
  // 明细: day→近7天, week→近7天, month→近30天
  getRecords(query: RevenueQuery): Promise<ApiResponse<RevenueRecord[]>> {
    const days = query.type === 'month' ? 30 : 7;
    return api.get('/business/revenue/daily', { params: { days } }).then((res) => ({
      ...res.data,
      data: (res.data?.data ?? []).map((d: Raw) => ({
        date: str(d.date),
        amount: num(d.net_revenue),
        orderCount: num(d.order_count),
      })),
    }));
  },
};
