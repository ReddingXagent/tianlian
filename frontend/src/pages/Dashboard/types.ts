/**
 * 天链 V3 - Dashboard 类型定义
 */

export interface HealthData {
  total_devices: number;
  healthy_devices: number;
  warning_devices: number;
  critical_devices: number;
  avg_health_score: number;
  health_rate: number;
}

export interface AlarmStats {
  total: number;
  active: number;
  critical: number;
  major: number;
  minor: number;
  info: number;
  trend?: Array<{ date: string; count: number }>;
}

export interface WorkOrderStats {
  pending: number;
  in_progress: number;
  completed: number;
  closed: number;
  cancelled: number;
}
