/**
 * types/modules/station.ts — 站点/充电桩类型
 */
export type StationStatus = 'online' | 'offline' | 'maintenance';
export type ChargerType = 'dc' | 'ac';
export type ConnectorStatus = 'idle' | 'charging' | 'offline' | 'fault';

export interface Station {
  id: number;
  name: string;
  address: string;
  status: StationStatus;
  latitude: number;
  longitude: number;
  distance?: number;
  pricePerKwh: number;
  serviceFee: number;
  totalConnectors: number;
  availableConnectors: number;
  chargingConnectors: number;
  isOpen24h: boolean;
  openingHours?: string;
  rating: number;
  createdAt: string;
  updatedAt: string;
}

export interface Charger {
  id: number;
  stationId: number;
  name: string;
  code: string;
  type: ChargerType;
  status: ConnectorStatus;
  power: number;
  pricePerKwh: number;
  serviceFee: number;
}

export interface StationQuery {
  keyword?: string;
  latitude?: number;
  longitude?: number;
  radius?: number;
  page?: number;
  pageSize?: number;
}

// 多租户品牌 (Tenant Branding — GET /tenants/{id}/branding)
export interface TenantBranding {
  tenantId: string;
  operatorName: string;
  logoUrl?: string;
  themeColor: string;
  source: 'default' | 'operator' | 'custom';
}
