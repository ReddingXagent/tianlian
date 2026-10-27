import { ApiResponse, ReportSummary, DeviceReport, AlarmReport } from '../types';
import api from './client';

// =====================
// 运维报表 API (GET /reports/summary)
// =====================
export const reportApi = {
  /** GET /reports/summary — 30天运维报表摘要 */
  getSummary(): Promise<ApiResponse<ReportSummary>> {
    return api.get('/reports/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const sh = (d.station_health as Record<string, unknown>) ?? {};
      const dist = (sh.distribution as Record<string, number>) ?? {};
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          overview: {
            totalDevices: (ov.total_devices as number) ?? 0,
            onlineDevices: (ov.online_devices as number) ?? 0,
            offlineDevices: (ov.offline_devices as number) ?? 0,
            faultDevices: (ov.fault_devices as number) ?? 0,
            maintenanceDevices: (ov.maintenance_devices as number) ?? 0,
            onlineRate: (ov.online_rate as number) ?? 0,
            totalStations: (ov.total_stations as number) ?? 0,
            totalWorkorders: (ov.total_workorders as number) ?? 0,
            completedWorkorders: (ov.completed_workorders as number) ?? 0,
            completionRate: (ov.completion_rate as number) ?? 0,
            totalAlarms: (ov.total_alarms as number) ?? 0,
            activeAlarms: (ov.active_alarms as number) ?? 0,
          },
          stationHealth: {
            normal: dist.normal ?? 0,
            warning: dist.warning ?? 0,
            critical: dist.critical ?? 0,
            offline: dist.offline ?? 0,
            healthyRate: (sh.healthy_rate as number) ?? 0,
          },
        },
      };
    });
  },
  /** GET /reports/devices — 30天设备报告 */
  getDevices(): Promise<ApiResponse<DeviceReport>> {
    return api.get('/reports/devices').then((res) => {
      const d = (res.data.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const typeDist = (d.type_distribution as Record<string, number>) ?? {};
      const statusDist = (d.status_distribution as Record<string, number>) ?? {};
      const stationDist = (d.station_distribution as Record<string, number>) ?? {};
      return {
        ...res.data,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalDevices: (ov.total_devices as number) ?? 0,
          onlineDevices: (ov.online_devices as number) ?? 0,
          offlineDevices: (ov.offline_devices as number) ?? 0,
          faultDevices: (ov.fault_devices as number) ?? 0,
          maintenanceDevices: (ov.maintenance_devices as number) ?? 0,
          typeDistribution: typeDist,
          statusDistribution: statusDist,
          stationDistribution: stationDist,
        },
      };
    });
  },
  /** GET /reports/alarms — 30天告警报告 */
  getAlarms(): Promise<ApiResponse<AlarmReport>> {
    return api.get('/reports/alarms').then((res) => {
      const d = (res.data.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const levelDist = (d.level_distribution as Record<string, number>) ?? {};
      const typeDist = (d.type_distribution as Record<string, number>) ?? {};
      const trend = (d.trend as Record<string, unknown>[]) ?? [];
      const topFaults = (d.top_fault_devices as Record<string, unknown>[]) ?? [];
      return {
        ...res.data,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalAlarms: (ov.total_alarms as number) ?? 0,
          activeAlarms: (ov.active_alarms as number) ?? 0,
          resolvedAlarms: (ov.resolved_alarms as number) ?? 0,
          levelDistribution: levelDist,
          typeDistribution: typeDist,
          trend: trend.map((t) => ({ date: (t.date as string) ?? '', count: (t.count as number) ?? 0 })),
          topFaultDevices: topFaults.map((f) => ({
            deviceId: (f.device_id as number) ?? (f.deviceId as number) ?? 0,
            deviceName: (f.device_name as string) ?? (f.deviceName as string) ?? '',
            alarmCount: (f.alarm_count as number) ?? (f.alarmCount as number) ?? 0,
          })),
        },
      };
    });
  },
};
