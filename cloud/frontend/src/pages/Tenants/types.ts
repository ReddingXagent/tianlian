/**
 * 运维团队管理类型定义
 *
 * 三级架构：SaaS平台 → 运维团队（客户）→ 光储充场站
 */

export interface Tenant {
  id: number;
  name: string;
  code: string;
  contact: string;
  phone?: string;
  email?: string;
  status: string;
  station_count: number;
  device_count: number;
  member_count: number;
  workorder_count: number;
  alarm_count: number;
  expired_at: string;
  storage_used?: string;
  api_calls?: number;
  created_at: string;
  address?: string;
  max_stations?: number;
  max_devices?: number;
  // 团队层级拆分：type / parent_team_id / parent_team_name
  type?: string;
  parent_team_id?: number | null;
  parent_team_name?: string | null;
  owner_subject_id?: number | null;
}

export interface TenantStats {
  total: number;
  active: number;
  trial: number;
  expired: number;
  total_stations: number;
  total_devices: number;
}

export interface TeamAccount {
  id: number;
  tenant_id: number;
  tenant_name: string;
  username: string;
  real_name: string;
  role: string;
  status: string;
  last_login: string;
  created_at: string;
}
