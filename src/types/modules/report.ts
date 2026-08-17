/**
 * types/modules/report.ts — 运维报表类型
 */
export interface ReportOverview {
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
}

export interface StationHealthDist {
  normal: number;
  warning: number;
  critical: number;
  offline: number;
  healthyRate: number;
}

export interface ReportSummary {
  periodDays: number;
  overview: ReportOverview;
  stationHealth: StationHealthDist;
}
