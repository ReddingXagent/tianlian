/**
 * types/modules/device.ts — 设备/设备健康/设备配置/设备报告类型
 */
import type { DeviceType, DeviceStatus } from '@tianlian/shared-types';
export { type DeviceType, type DeviceStatus } from '@tianlian/shared-types';

export interface Device {
  id: number;
  stationId: number;
  name: string;
  code: string;
  type: DeviceType;
  status: DeviceStatus;
  model: string;
  manufacturer: string;
  lastHeartbeat: string;
  createdAt: string;
  updatedAt: string;
}

export interface DeviceTelemetry {
  deviceId: number;
  power: number;
  voltage: number;
  current: number;
  temperature: number;
  energy: number;
  timestamp: string;
}

export interface DeviceHealth {
  deviceId: number;
  healthScore: number;
  healthStatus: 'excellent' | 'good' | 'warning' | 'critical';
  dimensionScores: Record<string, number>;
  checkedAt: string;
}

export interface DeviceConfig {
  deviceId: number;
  voltageLimit: number;
  currentLimit: number;
  maxPower: number;
  chargeMode: string;
  overloadProtection: boolean;
  timePeriods?: {
    start: string;
    end: string;
    maxPower: number;
  }[];
}

export interface DeviceReport {
  periodDays: number;
  totalDevices: number;
  onlineDevices: number;
  offlineDevices: number;
  faultDevices: number;
  maintenanceDevices: number;
  typeDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  stationDistribution: Record<string, number>;
}

export interface DeviceControlCommand {
  deviceId: number;
  command: 'start' | 'stop' | 'restart' | 'reset';
}

export interface DeviceControlLog {
  id: number;
  deviceId: number;
  deviceName: string;
  command: DeviceControlCommand['command'];
  commandLabel: string;
  status: 'success' | 'failed';
  message: string;
  operator: string;
  createdAt: string;
}
