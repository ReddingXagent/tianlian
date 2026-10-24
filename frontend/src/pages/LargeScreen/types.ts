/**
 * 天链V3 — 数据大屏类型定义
 *
 * Phase48: LargeScreen 数据契约
 */

export interface CoreMetrics {
  total_devices: number;
  online_devices: number;
  fault_devices: number;
  offline_devices: number;
  online_rate: number;
  total_stations: number;
  active_alarms: number;
  critical_alarms: number;
  pending_workorders: number;
  in_progress_workorders: number;
}

export interface HealthDistribution {
  excellent: number;
  good: number;
  warning: number;
  critical: number;
}

export interface StationHealth {
  station_id: number;
  station_name: string;
  health_score: number;
  device_count: number;
  online_count: number;
  fault_count: number;
}

export interface RecentAlarm {
  id: number;
  title: string;
  level: string;
  device_name: string;
  station_name: string;
  created_at: string | null;
}

export interface WorkOrderStats {
  pending: number;
  in_progress: number;
  completed: number;
  today_new_alarms: number;
}

export interface AlarmStats {
  active: number;
  critical: number;
  warning: number;
  today_new: number;
}

export interface DeviceTypeStat {
  type: string;
  total: number;
  online: number;
  rate: number;
}

export interface LargeScreenData {
  core_metrics: CoreMetrics;
  health_distribution: HealthDistribution;
  station_health: StationHealth[];
  recent_alarms: RecentAlarm[];
  workorder_stats: WorkOrderStats;
  alarm_stats: AlarmStats;
  device_type_stats: DeviceTypeStat[];
  timestamp: string;
}
