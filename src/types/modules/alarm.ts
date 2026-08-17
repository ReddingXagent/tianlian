/**
 * types/modules/alarm.ts — 告警相关类型
 */
export type AlarmType =
  | 'device_fault'
  | 'power_anomaly'
  | 'communication_loss'
  | 'temperature_warning'
  | 'other';

export type AlarmLevel = 'info' | 'warning' | 'critical';

export type AlarmStatus = 'unhandled' | 'processing' | 'resolved';

export interface Alarm {
  id: number;
  stationId: number;
  stationName: string;
  deviceId?: number;
  deviceName?: string;
  type: AlarmType;
  level: AlarmLevel;
  title: string;
  description: string;
  status: AlarmStatus;
  handledBy?: number;
  handledAt?: string;
  createdAt: string;
  updatedAt: string;
}

// 告警规则 (Alarm Rule — from /alarm-rules)
export interface AlarmRule {
  id: number;
  name: string;
  deviceType: string;
  metric: string;
  condition: string;
  threshold: number;
  level: AlarmLevel;
  enabled: boolean;
  description: string;
  createdAt: string;
  updatedAt: string;
}

export interface AlarmRuleCreate {
  name: string;
  metric: string;
  threshold: number;
  deviceType?: string;
  severity?: string;
  operator?: string;
  duration?: number;
  enabled?: boolean;
  description?: string;
}

export interface AlarmRuleUpdate {
  name?: string;
  metric?: string;
  threshold?: number;
  deviceType?: string;
  severity?: string;
  operator?: string;
  duration?: number;
  enabled?: boolean;
  description?: string;
}

export interface AlarmRuleCreated {
  id: number;
  name: string;
  description: string;
  deviceType: string | null;
  deviceIds: number[] | null;
  stationIds: number[] | null;
  metric: string;
  operator: string;
  threshold: number;
  duration: number;
  level: string;
  alarmTemplate: string;
  notifyUsers: string[] | null;
  autoCreateWorkorder: boolean;
  workorderPriority: string;
  enabled: boolean;
  silenceMinutes: number;
  createdAt: string;
  updatedAt: string | null;
}

// 告警报告 (Alarm Report — from /reports/alarms)
export interface AlarmReport {
  periodDays: number;
  totalAlarms: number;
  levelDistribution: Record<string, number>;
  typeDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  resolvedRate: number;
  activeAlarms: number;
  topFaultDevices: {
    deviceId: number;
    deviceName: string;
    alarmCount: number;
  }[];
  dailyTrend: {
    date: string;
    count: number;
  }[];
}
