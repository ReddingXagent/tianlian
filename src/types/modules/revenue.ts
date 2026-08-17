/**
 * types/modules/revenue.ts — 营收/看板类型
 */
export interface RevenueSummary {
  today: number;
  week: number;
  month: number;
  total: number;
}

export interface RevenueRecord {
  date: string;
  amount: number;
  orderCount: number;
}

export interface RevenueQuery {
  type: 'day' | 'week' | 'month';
  startDate?: string;
  endDate?: string;
}

export interface DashboardStats {
  totalStations: number;
  onlineStations: number;
  offlineStations: number;
  totalAlarms: number;
  unhandledAlarms: number;
  pendingWorkOrders?: number;
  totalWorkOrders?: number;
  revenueSummary?: RevenueSummary;
}
