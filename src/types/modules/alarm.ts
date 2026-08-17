/**
 * types/modules/alarm.ts — 告警类型
 */
import type { AlarmType, AlarmLevel, AlarmStatus, Alarm } from '@tianlian/shared-types';
export { type AlarmType, type AlarmLevel, type AlarmStatus, type Alarm } from '@tianlian/shared-types';

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
