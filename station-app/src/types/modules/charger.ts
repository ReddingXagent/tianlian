/**
 * types/modules/charger.ts — 充电桩监控类型
 */
import type { AlarmLevel } from './alarm';

export type ConnectorStatus = 'idle' | 'connected' | 'charging' | 'fault' | 'suspended';
export type ChargingState = 'idle' | 'preparing' | 'charging' | 'suspended' | 'finishing' | 'fault';
export type ChargerTrendMetric = 'power' | 'voltage' | 'current' | 'soc';

export interface ChargerStatus {
  id: number;
  deviceId: number;
  deviceName: string;
  connectorStatus: ConnectorStatus;
  power: number;
  voltage: number;
  current: number;
  temperature: number;
  soc?: number | null;
  energyTotal: number;
  sessionEnergy: number;
  sessionDuration: number;
  state: ChargingState;
  faultCode: string | null;
  faultMessage: string | null;
  lastHeartbeat: string;
  updatedAt: string;
}

export interface ChargerTrendPoint {
  timestamp: string;
  power: number;
  voltage: number;
  current: number;
  soc: number;
}

export interface ChargerTrend {
  deviceId: number;
  points: ChargerTrendPoint[];
}

export interface ChargerFaultRecord {
  id: number;
  chargerId: number;
  deviceId: number;
  faultCode: string;
  faultMessage: string;
  level: AlarmLevel;
  occurredAt: string;
  clearedAt: string | null;
  clearedBy: string | null;
}

export interface ChargerMonitorSummary {
  totalChargers: number;
  chargingCount: number;
  idleCount: number;
  faultCount: number;
  totalPower: number;
  todayEnergy: number;
  todaySessions: number;
  avgPowerPerCharger: number;
}
