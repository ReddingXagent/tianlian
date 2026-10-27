import { ApiResponse, DashboardStats, Alarm } from '../types';
import api from './client';
import { mapAlarm } from './mappers';
import { workOrderApi } from './work-order';
import { stationApi } from './station';

// =====================
// Dashboard API (真云端无专用端点, 聚合 work-orders/stats + alarms + stations)
// =====================
export const dashboardApi = {
  async getStats(): Promise<ApiResponse<DashboardStats>> {
    const [woStats, activeAlarms, allAlarms, stations] = await Promise.all([
      workOrderApi.getStats(),
      api.get('/alarms', { params: { status: 'active', page: 1, page_size: 1 } }),
      api.get('/alarms', { params: { page: 1, page_size: 1 } }),
      stationApi.getList({ page: 1, pageSize: 100 }),
    ]);
    const list = stations.data?.items ?? [];
    const online = list.filter((s) => s.status === 'online').length;
    return {
      code: 200,
      message: 'success',
      data: {
        totalStations: stations.data?.total ?? list.length,
        onlineStations: online,
        offlineStations: Math.max(0, (stations.data?.total ?? list.length) - online),
        totalAlarms: allAlarms.data?.data?.total ?? 0,
        unhandledAlarms: activeAlarms.data?.data?.total ?? 0,
        pendingWorkOrders: woStats.data?.status_distribution?.pending ?? 0,
        totalWorkOrders: woStats.data?.total ?? 0,
      },
    };
  },
  getRecentAlarms(limit = 5): Promise<ApiResponse<Alarm[]>> {
    return api.get('/alarms', { params: { page: 1, page_size: limit } }).then((res) => ({
      ...res.data,
      data: (res.data?.data?.items ?? []).map(mapAlarm),
    }));
  },
};
