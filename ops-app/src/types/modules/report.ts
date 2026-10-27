/**
 * types/modules/report.ts — 效率/利用率报告类型
 */
export interface EfficiencyReport {
  items: EfficiencyItem[];
  total: number;
  page: number;
  pageSize: number;
  alerts: {
    abnormalLowEfficiency: {
      count: number;
      threshold: string;
      items: EfficiencyItem[];
    };
  };
}

export interface EfficiencyItem {
  stationId?: number;
  stationName?: string;
  deviceId?: number;
  deviceName?: string;
  efficiency?: number;
  uptime?: number;
  utilization?: number;
}

export interface UtilizationReport {
  items: UtilizationItem[];
  total: number;
  page: number;
  pageSize: number;
  alerts: {
    lowUtilization: UtilizationAlertBucket;
    overload: UtilizationAlertBucket;
  };
}

export interface UtilizationItem {
  deviceId?: number;
  deviceName?: string;
  deviceCode?: string;
  deviceType?: string;
  stationId?: number;
  stationName?: string;
  utilizationRate?: number;
}

export interface UtilizationAlertBucket {
  count: number;
  threshold: string;
  items: UtilizationItem[];
}
