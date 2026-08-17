/**
 * types/modules/user.ts — 用户/角色/权限/工程师类型
 */
import type { UserRole } from '@tianlian/shared-types';
export { type UserRole } from '@tianlian/shared-types';

export interface User {
  id: number;
  username: string;
  nickname: string;
  email: string;
  phone: string;
  role: UserRole;
  avatar?: string;
  stationIds: number[];
  createdAt: string;
  updatedAt: string;
}

// 用户详情 (User Detail — from /users/{id})
export interface UserCreate {
  username: string;
  password?: string;
  realName?: string;
  phone?: string;
  role?: string;
  level?: string;
  teamId?: number;
}

export interface UserDetail {
  id: number;
  username: string;
  realName: string;
  phone: string | null;
  role: string;
  level: string;
  teamId: number | null;
  teamName: string | null;
  status: string;
  lastLogin: string;
  createdAt: string;
  updatedAt: string;
}

// 当前用户信息 (Auth Me — from /auth/me)
export interface AuthMe {
  id: number;
  username: string;
  realName: string;
  role: string;
  permissions: string[];
  teamType: string | null;
  teamId: number | null;
}

// 角色 (Role — from /roles)
export interface Role {
  id: number;
  name: string;
  displayName: string;
  description: string;
  isSystem: boolean;
  permissions: string[];
}

export interface RoleUpdate {
  displayName?: string;
  description?: string;
  permissions?: string[];
}

export interface RoleCreate {
  name: string;
  displayName?: string;
  description?: string;
  permissions?: string[];
}

// 权限树节点 (Permission Tree Node — from /roles/tree)
export interface PermissionTreeNode {
  key: string;
  title: string;
  resource: string;
  name?: string;
  action?: string;
  label?: string;
  isLeaf?: boolean;
  children?: PermissionTreeNode[];
}

// 权限项 (Permission — from /permissions)
export interface Permission {
  name: string;
  resource: string;
  action: string;
  label: string;
  labelShort: string;
}

// 工程师 (Engineer — from /engineers)
export interface Engineer {
  id: number;
  username: string;
  name: string;
  phone: string | null;
  level: 'junior' | 'senior' | 'expert';
  teamId: number | null;
  status: 'active' | 'inactive' | 'on_leave';
  role: string;
  createdAt: string;
  updatedAt: string;
}
