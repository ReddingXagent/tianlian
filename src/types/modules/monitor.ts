/**
 * types/modules/monitor.ts — 监控/扫码/诊断类型
 */
import type { DeviceStatus, DeviceType } from './device';
import type { KnowledgeArticle } from './knowledge';

export interface ScanResult {
  type: 'device' | 'station' | 'unknown';
  id: number;
  code: string;
  name?: string;
  status?: DeviceStatus;
}

export interface MonitorSummary {
  totalDevices: number;
  onlineDevices: number;
  faultDevices: number;
  criticalAlarms: number;
}

/** GET /monitor/realtime — 实时监控总览 */
export interface RealtimeOverview {
  totalPower: number;
  powerTrend: number;
  todayGeneration: number;
  todayConsumption: number;
  gridImport: number;
  gridExport: number;
  efficiency: number;
  updateTime: string;
  devices: RealtimeDeviceStatus[];
}

export interface RealtimeDeviceStatus {
  id: number;
  name: string;
  type: string;
  power: number;
  status: string;
}

// 故障诊断
export interface DiagnosisResult {
  faultCode: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  possibleCauses: string[];
  solutions: string[];
  relatedArticles?: KnowledgeArticle[];
  deviceType?: DeviceType;
}
