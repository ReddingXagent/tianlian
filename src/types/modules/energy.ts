/**
 * types/modules/energy.ts — 能源/报告概览类型
 */
export interface EnergySummary {
  period: string;
  days: number;
  pvGeneration: number;
  chargingAmount: number;
  dischargeAmount: number;
  pvRevenue: number;
  chargingRevenue: number;
  dischargeRevenue: number;
  totalRevenue: number;
  yoy: {
    pvGenerationYoy: number;
    chargingAmountYoy: number;
    dischargeAmountYoy: number;
    totalRevenueYoy: number;
  };
  priceInfo: {
    feedInTariff: number;
    chargingPrice: number;
    dischargePrice: number;
  };
}

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
