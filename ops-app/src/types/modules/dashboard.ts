/**
 * types/modules/dashboard.ts — 看板/工作台统计类型
 */
export interface DashboardStats {
  totalOrders: number;
  completedOrders: number;
  pendingOrders: number;
  avgCompletionHours: number;
  onTimeRate: number;
}

export interface DeviceHealthStats {
  total: number;
  online: number;
  offline: number;
  fault: number;
  maintenance: number;
  onlineRate: number;
}

export interface AlarmTrend {
  date: string;
  total: number;
  critical: number;
  warning: number;
  info: number;
}

export interface DashboardData {
  stats: DashboardStats;
  deviceHealth: DeviceHealthStats;
  alarmTrends: AlarmTrend[];
  workOrderTrends: import('./work-order').WorkOrderTrend[];
  topFaultDevices: {
    deviceId: number;
    deviceName: string;
    stationName: string;
    faultCount: number;
  }[];
}

export interface WorkbenchStats {
  pendingOrders: number;
  inProgressOrders: number;
  todayCompleted: number;
  unhandledAlarms: number;
  criticalAlarms: number;
}
