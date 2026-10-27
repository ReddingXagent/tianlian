/**
 * types/modules/device.ts — 设备相关类型
 */
import type { DeviceStatus, Device as SharedDevice } from '@tianlian/shared-types';
export { type DeviceType, type DeviceStatus } from '@tianlian/shared-types';

/** ops-app Device (共享基础 + stationName 扩展) */
export interface Device extends SharedDevice {
  stationName?: string;
}

export interface DeviceMetrics {
  deviceId: number;
  deviceName: string;
  temperature?: number;
  humidity?: number;
  voltage?: number;
  current?: number;
  power?: number;
  status: DeviceStatus;
  lastUpdated: string;
}

// 充电桩配置 (ChargerConfig — from /devices/{id}/config)
export interface ChargerConfig {
  deviceId: number;
  voltageLimit: number;
  currentLimit: number;
  maxPower: number;
  chargeMode: string;
  overloadProtection: boolean;
  timePeriods: {
    startTime: string;
    endTime: string;
    powerLimit: number;
  }[];
  createdAt: string | null;
  updatedAt: string | null;
}

// 设备健康度 (Device Health — from /devices/{id}/health)
export interface DeviceHealth {
  deviceId: number;
  deviceCode: string;
  deviceName: string;
  deviceType: string;
  healthScore: number;
  healthStatus: string;
  healthStatusDisplay: string;
  dimensionScores: Record<string, number>;
  checkedAt: string;
  lastHealthCheck: string | null;
}

// 设备健康摘要 (Device Health Summary — from /devices/health, 全局设备健康列表)
export interface DeviceHealthSummary {
  id: number;
  code: string;
  name: string;
  type: string;
  healthScore: number;
  status: string;
}

// 设备健康历史记录 (Device Health History — from /devices/{id}/health/history)
export interface DeviceHealthHistory {
  deviceId: number;
  healthScore: number;
  healthStatus: string;
  healthStatusDisplay: string;
  dimensionScores: Record<string, number>;
  checkedAt: string;
}

// 设备报告 (Device Report — from /reports/devices)
export interface DeviceReport {
  periodDays: number;
  totalDevices: number;
  typeDistribution: Record<string, number>;
  statusDistribution: Record<string, number>;
  stationDistribution: {
    stationId: number;
    stationName: string;
    deviceCount: number;
  }[];
  healthScore?: {
    average: number;
    distribution: Record<string, number>;
  };
  onlineRate?: number;
  faultRate?: number;
}

// 设备维保记录 (Device Maintenance Record — from /devices/{id}/maintenance-records)
export interface DeviceMaintenanceRecord {
  id: number;
  deviceId: number;
  type: string;
  title: string;
  description: string;
  status: string;
  scheduledDate: string | null;
  completedDate: string | null;
  engineerId: number | null;
  engineerName: string | null;
  cost: number | null;
  remark: string | null;
  createdAt: string;
  updatedAt: string | null;
}
