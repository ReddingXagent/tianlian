/**
 * api-modules/energy-report.ts — 能源与报表 API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api from './client';
import {
  ApiResponse,
  EnergySummary,
  EnergyTrendItem,
  ReportSummary,
  EfficiencyReport,
  UtilizationReport,
  UtilizationItem,
  DeviceReport,
  AlarmReport,
  WorkOrderReport,
} from '../../types';


export const energyApi = {
  getSummary(): Promise<ApiResponse<EnergySummary>> {
    return api.get('/energy/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const yoy = (d.yoy ?? {}) as Record<string, unknown>;
      const price = (d.price_info ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          period: (d.period as string) ?? 'month',
          days: (d.days as number) ?? 0,
          pvGeneration: (d.pv_generation as number) ?? 0,
          chargingAmount: (d.charging_amount as number) ?? 0,
          dischargeAmount: (d.discharge_amount as number) ?? 0,
          pvRevenue: (d.pv_revenue as number) ?? 0,
          chargingRevenue: (d.charging_revenue as number) ?? 0,
          dischargeRevenue: (d.discharge_revenue as number) ?? 0,
          totalRevenue: (d.total_revenue as number) ?? 0,
          yoy: {
            pvGenerationYoY: (yoy.pv_generation_yoy as number) ?? 0,
            chargingAmountYoY: (yoy.charging_amount_yoy as number) ?? 0,
            dischargeAmountYoY: (yoy.discharge_amount_yoy as number) ?? 0,
            totalRevenueYoY: (yoy.total_revenue_yoy as number) ?? 0,
          },
          priceInfo: {
            feedInTariff: (price.feed_in_tariff as number) ?? 0,
            chargingPrice: (price.charging_price as number) ?? 0,
            dischargePrice: (price.discharge_price as number) ?? 0,
          },
        },
      };
    });
  },

  /** GET /energy/trend — 31天光伏充电趋势 */
  getTrend(): Promise<ApiResponse<EnergyTrendItem[]>> {
    return api.get('/energy/trend').then((res) => {
      const raw = res.data as ApiResponse<{ trend?: Record<string, unknown>[] }>;
      const items = (raw.data?.trend ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((d) => ({
          date: (d.date as string) ?? '',
          pvGeneration: (d.pv_generation as number) ?? 0,
          chargingAmount: (d.charging_amount as number) ?? 0,
          dischargeAmount: (d.discharge_amount as number) ?? 0,
          pvRevenue: (d.pv_revenue as number) ?? 0,
          chargingRevenue: (d.charging_revenue as number) ?? 0,
          dischargeRevenue: (d.discharge_revenue as number) ?? 0,
          totalRevenue: (d.total_revenue as number) ?? 0,
        })),
      };
    });
  },
};

// =====================
// 用户管理 API

// =====================
export const reportApi = {
  /** GET /reports/summary — 30天运维报告概览 */
  getSummary(): Promise<ApiResponse<ReportSummary>> {
    return api.get('/reports/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const overview = (d.overview ?? {}) as Record<string, unknown>;
      const health = (d.station_health ?? {}) as Record<string, unknown>;
      const dist = (health.distribution ?? {}) as Record<string, unknown>;
      const team = (d.team_performance ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          overview: {
            totalDevices: (overview.total_devices as number) ?? 0,
            onlineDevices: (overview.online_devices as number) ?? 0,
            offlineDevices: (overview.offline_devices as number) ?? 0,
            faultDevices: (overview.fault_devices as number) ?? 0,
            maintenanceDevices: (overview.maintenance_devices as number) ?? 0,
            onlineRate: (overview.online_rate as number) ?? 0,
            totalStations: (overview.total_stations as number) ?? 0,
            totalWorkorders: (overview.total_workorders as number) ?? 0,
            completedWorkorders: (overview.completed_workorders as number) ?? 0,
            completionRate: (overview.completion_rate as number) ?? 0,
            totalAlarms: (overview.total_alarms as number) ?? 0,
            activeAlarms: (overview.active_alarms as number) ?? 0,
          },
          stationHealth: {
            distribution: {
              normal: (dist.normal as number) ?? 0,
              warning: (dist.warning as number) ?? 0,
              critical: (dist.critical as number) ?? 0,
              offline: (dist.offline as number) ?? 0,
            },
            healthyRate: (health.healthy_rate as number) ?? 0,
          },
          teamPerformance: {
            engineers: (team.engineers as unknown[]) ?? [],
            totalEngineers: (team.total_engineers as number) ?? 0,
            topEngineers: (team.top_engineers as unknown[]) ?? [],
          },
        },
      };
    });
  },

  /** GET /reports/devices — 30天设备报告 */
  getDeviceReport(): Promise<ApiResponse<DeviceReport>> {
    return api.get('/reports/devices').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalDevices: (d.total_devices as number) ?? 0,
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          stationDistribution: ((d.station_distribution as Record<string, unknown>[]) ?? []).map((s) => ({
            stationId: (s.station_id as number) ?? 0,
            stationName: (s.station_name as string) ?? '',
            deviceCount: (s.device_count as number) ?? 0,
          })),
          healthScore: (() => {
            const hs = d.health_score as Record<string, unknown> | undefined;
            if (!hs) return undefined;
            return {
              average: (hs.average as number) ?? 0,
              distribution: (hs.distribution as Record<string, number>) ?? {},
            };
          })(),
          onlineRate: (d.online_rate as number) ?? undefined,
          faultRate: (d.fault_rate as number) ?? undefined,
        },
      };
    });
  },

  /** GET /reports/alarms — 30天告警报告 */
  getAlarmReport(): Promise<ApiResponse<AlarmReport>> {
    return api.get('/reports/alarms').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalAlarms: (d.total_alarms as number) ?? 0,
          levelDistribution: (d.level_distribution as Record<string, number>) ?? {},
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          resolvedRate: (d.resolved_rate as number) ?? 0,
          activeAlarms: (d.active_alarms as number) ?? 0,
          topFaultDevices: ((d.top_fault_devices as Record<string, unknown>[]) ?? []).map((t) => ({
            deviceId: (t.device_id as number) ?? 0,
            deviceName: (t.device_name as string) ?? '',
            alarmCount: (t.alarm_count as number) ?? 0,
          })),
          dailyTrend: ((d.daily_trend as Record<string, unknown>[]) ?? []).map((t) => ({
            date: (t.date as string) ?? '',
            count: (t.count as number) ?? 0,
          })),
        },
      };
    });
  },

  /** GET /reports/workorders — 30天工单报告 */
  getWorkOrderReport(): Promise<ApiResponse<WorkOrderReport>> {
    return api.get('/reports/workorders').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const eff = (d.efficiency ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalWorkorders: (d.total_workorders as number) ?? 0,
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          levelDistribution: (d.level_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          completionRate: (d.completion_rate as number) ?? 0,
          efficiency: {
            avgResponseHours: (eff.avg_response_hours as number) ?? 0,
            avgCompletionHours: (eff.avg_completion_hours as number) ?? 0,
          },
          engineerPerformance: ((d.engineer_performance as Record<string, unknown>[]) ?? []).map((e) => ({
            engineerId: (e.engineer_id as number) ?? 0,
            engineerName: (e.engineer_name as string) ?? '',
            completedCount: (e.completed_count as number) ?? 0,
            avgCompletionHours: (e.avg_completion_hours as number) ?? 0,
          })),
        },
      };
    });
  },

  /** GET /reports/efficiency — 效率报告 */
  getEfficiency(params?: {
    period?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<EfficiencyReport>> {
    return api.get('/reports/efficiency', { params: { period: params?.period, page: params?.page, page_size: params?.pageSize } }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const alerts = (d.alerts ?? {}) as Record<string, unknown>;
      const abnormal = (alerts.abnormal_low_efficiency ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          items: ((d.items as Record<string, unknown>[]) ?? []).map((item) => ({
            stationId: (item.station_id as number) ?? undefined,
            stationName: (item.station_name as string) ?? undefined,
            deviceId: (item.device_id as number) ?? undefined,
            deviceName: (item.device_name as string) ?? undefined,
            efficiency: (item.efficiency as number) ?? undefined,
            uptime: (item.uptime as number) ?? undefined,
            utilization: (item.utilization as number) ?? undefined,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
          alerts: {
            abnormalLowEfficiency: {
              count: (abnormal.count as number) ?? 0,
              threshold: (abnormal.threshold as string) ?? '',
              items: ((abnormal.items as Record<string, unknown>[]) ?? []).map((item) => ({
                stationId: (item.station_id as number) ?? undefined,
                stationName: (item.station_name as string) ?? undefined,
                deviceId: (item.device_id as number) ?? undefined,
                deviceName: (item.device_name as string) ?? undefined,
                efficiency: (item.efficiency as number) ?? undefined,
                uptime: (item.uptime as number) ?? undefined,
                utilization: (item.utilization as number) ?? undefined,
              })),
            },
          },
        },
      };
    });
  },

  /** GET /reports/utilization — 设备利用率报告 */
  getUtilization(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<UtilizationReport>> {
    return api.get('/reports/utilization', { params: { page: params?.page, page_size: params?.pageSize } }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const alerts = (d.alerts ?? {}) as Record<string, unknown>;
      const lowUtil = (alerts.low_utilization ?? {}) as Record<string, unknown>;
      const overload = (alerts.overload ?? {}) as Record<string, unknown>;
      const mapItem = (item: Record<string, unknown>): UtilizationItem => ({
        deviceId: (item.device_id as number) ?? undefined,
        deviceName: (item.device_name as string) ?? undefined,
        deviceCode: (item.device_code as string) ?? undefined,
        deviceType: (item.device_type as string) ?? undefined,
        stationId: (item.station_id as number) ?? undefined,
        stationName: (item.station_name as string) ?? undefined,
        utilizationRate: (item.utilization_rate as number) ?? undefined,
      });
      return {
        ...raw,
        data: {
          items: ((d.items as Record<string, unknown>[]) ?? []).map(mapItem),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
          alerts: {
            lowUtilization: {
              count: (lowUtil.count as number) ?? 0,
              threshold: (lowUtil.threshold as string) ?? '',
              items: ((lowUtil.items as Record<string, unknown>[]) ?? []).map(mapItem),
            },
            overload: {
              count: (overload.count as number) ?? 0,
              threshold: (overload.threshold as string) ?? '',
              items: ((overload.items as Record<string, unknown>[]) ?? []).map(mapItem),
            },
          },
        },
      };
    });
  },
};

// =====================
// 告警规则 API (GET /alarm-rules)
// =====================
