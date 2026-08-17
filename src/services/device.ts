import { ApiResponse, Device, DeviceTelemetry, DeviceHealth, DeviceConfig, PaginatedData } from '../types';
import api from './client';

// =====================
// 设备 API
// =====================
export const deviceApi = {
  getList(params?: { stationId?: number; page?: number; pageSize?: number; search?: string; status?: string; sort?: string }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/devices', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Device>> {
    return api.get(`/devices/${id}`).then((res) => res.data);
  },
  getTelemetry(deviceId: number): Promise<ApiResponse<DeviceTelemetry>> {
    return api.get(`/devices/${deviceId}/telemetry`).then((res) => res.data);
  },
  getHealth(deviceId: number): Promise<ApiResponse<DeviceHealth>> {
    return api.get(`/devices/${deviceId}/health`).then((res) => {
      const d = res.data.data;
      return {
        ...res.data,
        data: {
          deviceId: d.device_id ?? d.deviceId ?? deviceId,
          healthScore: d.health_score ?? d.healthScore ?? 0,
          healthStatus: d.health_status ?? d.healthStatus ?? 'good',
          dimensionScores: d.dimension_scores ?? d.dimensionScores ?? {},
          checkedAt: d.checked_at ?? d.checkedAt ?? new Date().toISOString(),
        },
      };
    });
  },
  controlDevice(deviceId: number, command: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post(`/devices/${deviceId}/control`, { command }).then((res) => res.data);
  },
  /** GET /devices/{id}/config — 充电桩配置 (仅充电桩设备) */
  getConfig(deviceId: number): Promise<ApiResponse<DeviceConfig>> {
    return api.get(`/devices/${deviceId}/config`).then((res) => {
      const d = res.data.data;
      return {
        ...res.data,
        data: {
          deviceId: d.device_id ?? d.deviceId ?? deviceId,
          voltageLimit: d.voltage_limit ?? d.voltageLimit ?? 0,
          currentLimit: d.current_limit ?? d.currentLimit ?? 0,
          maxPower: d.max_power ?? d.maxPower ?? 0,
          chargeMode: d.charge_mode ?? d.chargeMode ?? 'standard',
          overloadProtection: d.overload_protection ?? d.overloadProtection ?? false,
          timePeriods: (d.time_periods ?? d.timePeriods ?? []).map((p: Record<string, unknown>) => ({
            start: (p.start as string) ?? '',
            end: (p.end as string) ?? '',
            maxPower: (p.max_power as number) ?? (p.maxPower as number) ?? 0,
          })),
        },
      };
    });
  },
};
