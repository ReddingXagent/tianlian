/**
 * types/modules/energy.ts — 能源/报告概览类型
 */
import type { EnergyYoY, EnergyPriceInfo, EnergySummary } from '@tianlian/shared-types';
export { type EnergyYoY, type EnergyPriceInfo, type EnergySummary } from '@tianlian/shared-types';

// ops-app 专属能源类型 (EnergyTrendItem / ReportSummary 保留仓内)

export interface EnergyTrendItem {
  date: string;
  pvGeneration: number;
  chargingAmount: number;
  dischargeAmount: number;
  pvRevenue: number;
  chargingRevenue: number;
  dischargeRevenue: number;
  totalRevenue: number;
}

// 报告概览 (Report Summary)
export interface ReportSummary {
  periodDays: number;
  overview: {
    totalDevices: number;
    onlineDevices: number;
    offlineDevices: number;
    faultDevices: number;
    maintenanceDevices: number;
    onlineRate: number;
    totalStations: number;
    totalWorkorders: number;
    completedWorkorders: number;
    completionRate: number;
    totalAlarms: number;
    activeAlarms: number;
  };
  stationHealth: {
    distribution: {
      normal: number;
      warning: number;
      critical: number;
      offline: number;
    };
    healthyRate: number;
  };
  teamPerformance: {
    engineers: unknown[];
    totalEngineers: number;
    topEngineers: unknown[];
  };
}
