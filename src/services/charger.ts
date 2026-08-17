import { ApiResponse, ChargerStatus, ChargerMonitorSummary, ChargerTrend, ChargerFaultRecord, PaginatedData } from '../types';
import api from './client';

// =====================
// 充电桩监控 API
// =====================
export const chargerApi = {
  getMonitorList(stationId: number): Promise<ApiResponse<ChargerStatus[]>> {
    return api.get(`/stations/${stationId}/chargers/monitor`).then((res) => res.data);
  },
  getMonitorSummary(stationId: number): Promise<ApiResponse<ChargerMonitorSummary>> {
    return api.get(`/stations/${stationId}/chargers/summary`).then((res) => res.data);
  },
  getFaultRecords(params: {
    stationId?: number;
    deviceId?: number;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<ChargerFaultRecord>>> {
    return api.get('/chargers/faults', { params }).then((res) => res.data);
  },
  clearFault(faultId: number): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post(`/chargers/faults/${faultId}/clear`).then((res) => res.data);
  },
  // 充电桩实时趋势（功率/电压/电流/SOC 历史曲线）
  getTrend(deviceId: number, params?: { points?: number }): Promise<ApiResponse<ChargerTrend>> {
    return api.get(`/devices/${deviceId}/charger-trend`, { params }).then((res) => res.data);
  },
};
