/**
 * 核心类型定义 - 精简版本，用于常用导入
 */

// ==================== 通用 ====================
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  timestamp: number;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type UserRole = 'ADMIN' | 'ENGINEER' | 'TECHNICIAN' | 'OPERATOR' | 'VIEWER';
export type DeviceType = 'solar' | 'storage' | 'charger' | 'inverter' | 'transformer' | 'meter' | 'sensor' | 'controller' | 'gateway';
export type DeviceStatus = 'online' | 'offline' | 'maintenance' | 'fault' | 'idle' | 'standby';
export type AlarmLevel = 'critical' | 'major' | 'minor' | 'info';
export type AlarmStatus = 'active' | 'acknowledged' | 'resolved' | 'suppressed';
export type WorkOrderType = 'repair' | 'maintenance' | 'inspection' | 'emergency' | 'upgrade' | 'calibration';
export type WorkOrderStatus = 'pending' | 'in_progress' | 'completed' | 'closed' | 'cancelled';
export type WorkOrderPriority = 'urgent' | 'high' | 'medium' | 'low';
export type TenantStatus = 'active' | 'trial' | 'expired' | 'disabled' | 'suspended';
export type EntryType = 'platform' | 'ops';
export type UserType = 'admin' | 'engineer' | 'operator' | 'fleet';

// ==================== 常用实体 ====================
export interface User {
  id: number;
  username: string;
  real_name: string;
  phone?: string;
  email?: string;
  role: UserRole;
  status: string;
  team_id?: number;
  created_at: string;
  updated_at: string;
}

export interface Station {
  id: number;
  name: string;
  code: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  status: string;
  capacity_kw?: number;
  operator_id?: number;
  device_count?: number;
  created_at: string;
}

export interface Device {
  id: number;
  name: string;
  sn: string;
  type: DeviceType;
  model?: string;
  status: DeviceStatus;
  station_id: number;
  ip_address?: string;
  firmware_version?: string;
  health_score?: number;
  last_online?: string;
  created_at: string;
}

export interface Alarm {
  id: number;
  title: string;
  description?: string;
  level: AlarmLevel;
  status: AlarmStatus;
  station_id?: number;
  device_id?: number;
  handler_id?: number;
  created_at: string;
  updated_at?: string;
}

export interface WorkOrder {
  id: number;
  title: string;
  description?: string;
  type: WorkOrderType;
  status: WorkOrderStatus;
  priority: WorkOrderPriority;
  creator_id: number;
  assignee_id?: number;
  station_id?: number;
  device_id?: number;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
}

export interface Tenant {
  id: number;
  name: string;
  code: string;
  contact: string;
  phone?: string;
  email?: string;
  address?: string;
  status: TenantStatus;
  station_count: number;
  device_count: number;
  member_count: number;
  max_stations: number;
  max_devices: number;
  expired_at: string;
  storage_used: string;
  api_calls: number;
  created_at: string;
}

export interface Gateway {
  id: number;
  sn: string;
  name: string;
  model?: string;
  status: string;
  firmware_version?: string;
  health_score?: number;
  ip_address?: string;
  last_online?: string;
  station_id?: number;
}

// ==================== 实用工具 ====================
export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type Dictionary<T = any> = Record<string, T>;