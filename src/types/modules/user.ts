/**
 * types/modules/user.ts — 用户/认证类型
 */
export type UserRole = 'admin' | 'station_master' | 'operator' | 'viewer';

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

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}
