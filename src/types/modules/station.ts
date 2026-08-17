/**
 * types/modules/station.ts — 站点类型
 */
export type StationStatus = 'online' | 'offline' | 'maintenance';

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
