/**
 * types/modules/alarm.ts — 告警类型
 */
export type AlarmType = 'device_fault' | 'power_anomaly' | 'communication_loss' | 'temperature_warning' | 'other';
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

export interface AlarmQuery {
  stationId?: number;
  level?: AlarmLevel;
  status?: AlarmStatus;
  page?: number;
  pageSize?: number;
}

export interface AlarmReport {
  periodDays: number;
  totalAlarms: number;
  activeAlarms: number;
  resolvedAlarms: number;
  levelDistribution: Record<string, number>;
  typeDistribution: Record<string, number>;
  trend: {
    date: string;
    count: number;
  }[];
  topFaultDevices: {
    deviceId: number;
    deviceName: string;
    alarmCount: number;
  }[];
}
