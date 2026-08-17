/**
 * types/modules/station.ts — 站点类型
 */
import type { StationStatus } from '@tianlian/shared-types';
export { type StationStatus } from '@tianlian/shared-types';

export interface Station {
  id: number;
  name: string;
  code: string;
  address: string;
  status: StationStatus;
  latitude: number;
  longitude: number;
  deviceCount: number;
  onlineDeviceCount: number;
  alarmCount: number;
  healthScore?: number;
  totalPower?: number;
  createdAt: string;
  updatedAt: string;
}
