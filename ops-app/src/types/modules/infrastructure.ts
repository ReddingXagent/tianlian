/**
 * types/modules/infrastructure.ts — 设施/备件/网关/VPP/租户/团队/车队类型
 */
// 备件 (SparePart — from /spare-parts)
export interface SparePart {
  id: number;
  partName: string;
  partModel: string | null;
  totalQuantity: number;
  availableQuantity: number;
  warehouse: string;
  createdAt: string;
}

export interface SparePartCreate {
  partName: string;
  partModel?: string | null;
  totalQuantity?: number;
  availableQuantity?: number;
  warehouse?: string;
}

// 网关 (Gateway — from /gateways)
export interface Gateway {
  id: number;
  sn: string;
  name: string;
  model: string | null;
  manufacturer: string | null;
  stationId: number | null;
  status: 'online' | 'offline' | 'warning';
  firmwareVersion: string | null;
  lastOnline: string | null;
  ipAddress: string | null;
  macAddress: string | null;
  location: string | null;
  healthScore: number;
  createdAt: string;
  updatedAt: string;
  notes: string | null;
}

// 网关固件包 (from /gateways/firmware)
export interface GatewayFirmware {
  id: number;
  version: string;
  fileId: string | null;
  fileSize: number | null;
  releaseNotes: string | null;
  status: string | null;
  createdAt: string;
  updatedAt: string | null;
}

// 网关状态统计 (from /gateways/status)
export interface GatewayStatus {
  onlineCount: number;
  offlineCount: number;
  maintenanceCount: number;
  faultCount: number;
  total: number;
}

// VPP 虚拟电厂资源 (from /vpp/resources)
export type VppResourceType = 'pv' | 'battery' | 'ev' | 'load';

export interface VppResource {
  resourceId: string;
  resourceType: VppResourceType;
  stationId: string;
  ratedPowerKw: number;
  currentPowerKw: number;
  availablePowerKw: number;
  soc: number | null;
  efficiency: number;
  priority: number;
  costPerKwh: number;
}

// VPP 调度 (from POST /vpp/dispatch)
export type VppDispatchMode = 'peak_shaving' | 'valley_filling' | 'frequency_regulation' | 'demand_response';

export interface VppDispatchCommand {
  resourceId: string;
  stationId: string;
  resourceType: VppResourceType;
  targetPowerKw: number;
  durationMin: number;
  priority: number;
  estimatedRevenue: number;
  estimatedCost: number;
  dispatchMode: VppDispatchMode;
}

export interface VppDispatchPlan {
  planId: string;
  mode: VppDispatchMode;
  trigger: string;
  stationsInvolved: string[];
  totalDispatchKw: number;
  estimatedRevenue: number;
  estimatedCost: number;
  netProfit: number;
  commands: VppDispatchCommand[];
  createdAt: string;
}

export interface VppDispatchHistory {
  planId: string;
  mode: VppDispatchMode;
  trigger: string;
  stationsInvolved: string[];
  totalDispatchKw: number;
  estimatedRevenue: number;
  estimatedCost: number;
  netProfit: number;
  commandsCount: number;
  createdAt: string;
  executed: boolean;
}

// 租户 (Tenant — from /tenants)
export interface Tenant {
  id: number;
  name: string;
  code: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

// 运维团队 (from GET /teams)
export interface Team {
  id: number;
  name: string;
  code: string | null;
  leaderId: number | null;
  leaderName: string | null;
  description: string | null;
  memberCount: number;
  stationCount: number;
  status: string;
  createdAt: string | null;
}

export interface TeamUpdate {
  name?: string;
  description?: string;
  leaderId?: number | null;
  status?: string;
}

export interface TeamCreate {
  name: string;
  code?: string;
  description?: string;
}

// 团队成员 (TeamMember — from POST /teams/{id}/members, GET /teams/{id}/members)
export interface TeamMember {
  id: number;
  userId: number;
  username: string;
  realName: string | null;
  teamId: number;
  role: string;
  level: string | null;
  phone: string | null;
  status: string;
  joinDate: string | null;
}

export interface TeamMemberAdd {
  userId: number;
  role?: string;
}

// 车队司机 (from GET /fleet/drivers)
export interface FleetDriver {
  id: number;
  name: string;
  phone: string | null;
  licenseNumber: string | null;
  vehiclePlate: string | null;
  status: string;
  createdAt: string | null;
  updatedAt: string | null;
}

// Webhook (from /webhooks)
export interface Webhook {
  id: number;
  name: string;
  url: string;
  events: string[];
  secret: string | null;
  enabled: boolean;
  lastTriggeredAt: string | null;
  lastResponseStatus: number | null;
  createdAt: string;
  updatedAt: string;
}
