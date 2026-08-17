/**
 * api-modules/auth.ts — 认证 + 工作台 API
 * 从 services/api.ts 拆分 (F1360 维度21 结构重构)
 */
import api from './client';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  RefreshTokenResponse,
  WorkbenchStats,
  WorkOrder,
  Alarm,
  AuthMe,
} from '../../types';

export const authApi = {
  login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    return api.post('/auth/login', data).then((res) => res.data);
  },
  logout(): Promise<ApiResponse<null>> {
    return api.post('/auth/logout').then((res) => res.data);
  },
  /** POST /auth/refresh — 刷新访问令牌 */
  refreshToken(): Promise<ApiResponse<RefreshTokenResponse>> {
    return api.post('/auth/refresh').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          accessToken: (d.access_token as string) ?? '',
          tokenType: (d.token_type as string) ?? 'bearer',
          expiresIn: (d.expires_in as number) ?? 0,
        },
      };
    });
  },
  /** GET /auth/me — 当前登录用户信息 + 权限列表 */
  getProfile(): Promise<ApiResponse<AuthMe>> {
    return api.get('/auth/me').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          username: (d.username as string) ?? '',
          realName: (d.real_name as string) ?? '',
          role: (d.role as string) ?? '',
          permissions: (d.permissions as string[]) ?? [],
          teamType: (d.team_type as string) ?? null,
          teamId: (d.team_id as number) ?? null,
        },
      };
    });
  },
};

export const workbenchApi = {
  getStats(): Promise<ApiResponse<WorkbenchStats>> {
    return api.get('/workbench/stats').then((res) => res.data);
  },
  getPendingOrders(limit?: number): Promise<ApiResponse<WorkOrder[]>> {
    return api.get('/workbench/pending-orders', { params: { limit } }).then((res) => res.data);
  },
  getRecentAlarms(limit?: number): Promise<ApiResponse<Alarm[]>> {
    return api.get('/workbench/recent-alarms', { params: { limit } }).then((res) => res.data);
  },
};
