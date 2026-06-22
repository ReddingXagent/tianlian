import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  User,
  Station,
  Device,
  Alarm,
  WorkOrder,
  PaginatedData,
  DashboardStats,
  RevenueRecord,
  RevenueQuery,
  DeviceTelemetry,
  CreateWorkOrderData,
  ChargerStatus,
  ChargerMonitorSummary,
  AppNotification,
} from '../types';

const TOKEN_KEY = 'auth_token';
const BASE_URL = 'http://8.134.106.166/api/v1';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// JWT token 注入拦截器
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // SecureStore 失败时静默处理
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// 401 响应拦截器 - token 过期自动清除
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      } catch {
        // 静默处理
      }
    }
    return Promise.reject(error);
  }
);

// =====================
// Token 管理
// =====================
export const tokenStorage = {
  async getToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  async setToken(token: string): Promise<void> {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  },
  async removeToken(): Promise<void> {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  },
};

// =====================
// 认证 API
// =====================
export const authApi = {
  login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    return api.post('/auth/login', data).then((res) => res.data);
  },
  logout(): Promise<ApiResponse<null>> {
    return api.post('/auth/logout').then((res) => res.data);
  },
  getProfile(): Promise<ApiResponse<User>> {
    return api.get('/auth/profile').then((res) => res.data);
  },
};

// =====================
// 站点 API
// =====================
export const stationApi = {
  getList(params?: { page?: number; pageSize?: number; search?: string }): Promise<ApiResponse<PaginatedData<Station>>> {
    return api.get('/stations', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => res.data);
  },
  getDevices(stationId: number): Promise<ApiResponse<Device[]>> {
    return api.get(`/stations/${stationId}/devices`).then((res) => res.data);
  },
  getAlarms(stationId: number, params?: { page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    return api.get(`/stations/${stationId}/alarms`, { params }).then((res) => res.data);
  },
};

// =====================
// 设备 API
// =====================
export const deviceApi = {
  getList(params?: { stationId?: number; page?: number; pageSize?: number; search?: string; status?: string; sort?: string }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/devices', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Device>> {
    return api.get(`/devices/${id}`).then((res) => res.data);
  },
  getTelemetry(deviceId: number): Promise<ApiResponse<DeviceTelemetry>> {
    return api.get(`/devices/${deviceId}/telemetry`).then((res) => res.data);
  },
  controlDevice(deviceId: number, command: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post(`/devices/${deviceId}/control`, { command }).then((res) => res.data);
  },
};

// =====================
// 告警 API
// =====================
export const alarmApi = {
  getList(params?: {
    stationId?: number;
    level?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    return api.get('/alarms', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Alarm>> {
    return api.get(`/alarms/${id}`).then((res) => res.data);
  },
  handleAlarm(id: number): Promise<ApiResponse<Alarm>> {
    return api.post(`/alarms/${id}/handle`).then((res) => res.data);
  },
};

// =====================
// 工单 API
// =====================
export const workOrderApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    return api.get('/work-orders', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => res.data);
  },
  createWorkOrder(data: CreateWorkOrderData): Promise<ApiResponse<WorkOrder>> {
    return api.post('/work-orders', data).then((res) => res.data);
  },
  completeWorkOrder(id: number): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/complete`).then((res) => res.data);
  },
};

// =====================
// Dashboard API
// =====================
export const dashboardApi = {
  getStats(): Promise<ApiResponse<DashboardStats>> {
    return api.get('/dashboard/stats').then((res) => res.data);
  },
  getRecentAlarms(limit?: number): Promise<ApiResponse<Alarm[]>> {
    return api.get('/dashboard/recent-alarms', { params: { limit } }).then((res) => res.data);
  },
};

// =====================
// 营收 API
// =====================
export const revenueApi = {
  getSummary(): Promise<ApiResponse<{ today: number; week: number; month: number; total: number }>> {
    return api.get('/revenue/summary').then((res) => res.data);
  },
  getRecords(query: RevenueQuery): Promise<ApiResponse<RevenueRecord[]>> {
    return api.get('/revenue/records', { params: query }).then((res) => res.data);
  },
};

// =====================
// 充电桩监控 API
// =====================
export const chargerApi = {
  getMonitorList(stationId: number): Promise<ApiResponse<ChargerStatus[]>> {
    return api.get(`/stations/${stationId}/chargers/monitor`).then((res) => res.data);
  },
  getMonitorSummary(stationId: number): Promise<ApiResponse<ChargerMonitorSummary>> {
    return api.get(`/stations/${stationId}/chargers/summary`).then((res) => res.data);
  },
  getFaultRecords(params: {
    stationId?: number;
    deviceId?: number;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<import('../types').ChargerFaultRecord>>> {
    return api.get('/chargers/faults', { params }).then((res) => res.data);
  },
  clearFault(faultId: number): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post(`/chargers/faults/${faultId}/clear`).then((res) => res.data);
  },
};

// =====================
// 通知 API
// =====================
export const notificationApi = {
  getList(params?: {
    page?: number;
    pageSize?: number;
    unreadOnly?: boolean;
  }): Promise<ApiResponse<PaginatedData<AppNotification>>> {
    return api.get('/notifications', { params }).then((res) => res.data);
  },
  getUnreadCount(): Promise<ApiResponse<{ count: number }>> {
    return api.get('/notifications/unread-count').then((res) => res.data);
  },
  markAsRead(id: number): Promise<ApiResponse<AppNotification>> {
    return api.post(`/notifications/${id}/read`).then((res) => res.data);
  },
  markAllAsRead(): Promise<ApiResponse<null>> {
    return api.post('/notifications/read-all').then((res) => res.data);
  },
};

export default api;