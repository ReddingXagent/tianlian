/**
 * types/modules/station.ts — 站点相关类型
 */
export type StationStatus = 'online' | 'offline' | 'maintenance' | 'normal';

export interface StationBranding {
  operatorName: string;
  logoUrl: string;
  servicePhone: string;
  themeColor: string;
  source: string;
}

export interface Station {
  id: number;
  name: string;
  code: string;
  province: string;
  city: string;
  district: string;
  address: string;
  lat: number;
  lon: number;
  status: StationStatus;
  stationType: string | null;
  operatorId: number | null;
  operatorName: string | null;
  teamId: number | null;
  totalPower: number;
  totalDevices: number;
  gunCount: number;
  venueType: string | null;
  totalCost: number | null;
  parkingSpots: number | null;
  healthScore: number;
  branding: StationBranding | null;
  createdAt: string;
  updatedAt: string | null;
}

export interface StationCreate {
  name: string;
  code?: string;
  province?: string;
  city?: string;
  district?: string;
  address?: string;
  lat?: number;
  lon?: number;
  stationType?: string;
  operatorId?: number;
  teamId?: number;
  totalPower?: number;
  venueType?: string;
  totalCost?: number;
  parkingSpots?: number;
}
