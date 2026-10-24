/**
 * 天链 V3 - 系统配置页面类型定义
 */

export interface PermissionItem {
  name: string;
  resource: string;
  action: string;
  label: string;
}

export interface RoleItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
  user_count: number;
}

export interface NotificationRule {
  id: number;
  name: string;
  level: string;
  channels: string[];
  receivers: string[];
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface LogItem {
  id: number;
  timestamp: string;
  username: string;
  action: string;
  module: string;
  target_id: string | null;
  target_desc: string | null;
  detail: string | null;
  ip_address: string | null;
  result: string;
}
