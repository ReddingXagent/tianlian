import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  User,
  WorkOrder,
  Alarm,
  Device,
  DeviceMetrics,
  MonitorSummary,
  KnowledgeArticle,
  ScanResult,
  PaginatedData,
  WorkbenchStats,
  DiagnosisResult,
  WorkOrderRecord,
  InspectionTask,
  DashboardData,
  AlarmTrend,
  WorkOrderTrend,
  DeviceHealthStats,
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
// 工作台 API
// =====================
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

// =====================
// 工单 API
// =====================
export const workOrderApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    priority?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    return api.get('/work-orders', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => res.data);
  },
  create(data: Partial<WorkOrder>): Promise<ApiResponse<WorkOrder>> {
    return api.post('/work-orders', data).then((res) => res.data);
  },
  update(id: number, data: Partial<WorkOrder>): Promise<ApiResponse<WorkOrder>> {
    return api.put(`/work-orders/${id}`, data).then((res) => res.data);
  },
  updateStatus(id: number, status: string): Promise<ApiResponse<WorkOrder>> {
    return api.patch(`/work-orders/${id}/status`, { status }).then((res) => res.data);
  },
  assign(id: number, assigneeId: number): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/assign`, { assigneeId }).then((res) => res.data);
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
// 设备 API
// =====================
export const deviceApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/devices', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Device>> {
    return api.get(`/devices/${id}`).then((res) => res.data);
  },
  getMetrics(id: number): Promise<ApiResponse<DeviceMetrics>> {
    return api.get(`/devices/${id}/metrics`).then((res) => res.data);
  },
};

// =====================
// 监控 API
// =====================
export const monitorApi = {
  getSummary(): Promise<ApiResponse<MonitorSummary>> {
    return api.get('/monitor/summary').then((res) => res.data);
  },
  getFaultDevices(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/monitor/faults', { params }).then((res) => res.data);
  },
  getCriticalAlarms(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    return api.get('/monitor/critical-alarms', { params }).then((res) => res.data);
  },
};

// =====================
// 扫码 API
// =====================
export const scanApi = {
  scan(code: string): Promise<ApiResponse<ScanResult>> {
    return api.post('/scan', { code }).then((res) => res.data);
  },
  scanDevice(deviceCode: string): Promise<ApiResponse<Device>> {
    return api.post('/scan/device', { code: deviceCode }).then((res) => res.data);
  },
  checkIn(deviceId: number, location?: { lat: number; lng: number }): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post('/scan/check-in', { deviceId, location }).then((res) => res.data);
  },
};

// =====================
// 知识库 API
// =====================
export const knowledgeApi = {
  getList(params?: {
    category?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<KnowledgeArticle>>> {
    return api.get('/knowledge', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<KnowledgeArticle>> {
    return api.get(`/knowledge/${id}`).then((res) => res.data);
  },
  search(query: string): Promise<ApiResponse<KnowledgeArticle[]>> {
    return api.get('/knowledge/search', { params: { q: query } }).then((res) => res.data);
  },
};

// =====================
// 诊断 API
// =====================
export const diagnosisApi = {
  getDiagnosis(faultCode: string): Promise<ApiResponse<DiagnosisResult>> {
    return api.get('/diagnosis', { params: { code: faultCode } }).then((res) => res.data);
  },
};

// =====================
// 工单执行记录 API
// =====================
export const workOrderRecordApi = {
  getRecords(orderId: number): Promise<ApiResponse<WorkOrderRecord[]>> {
    return api.get(`/work-orders/${orderId}/records`).then((res) => res.data);
  },
  addRecord(orderId: number, data: { action: string; note: string }): Promise<ApiResponse<WorkOrderRecord>> {
    return api.post(`/work-orders/${orderId}/records`, data).then((res) => res.data);
  },
};

// =====================
// 工单操作 API（语义化方法）
// =====================
export const workOrderActionApi = {
  accept(id: number): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/accept`).then((res) => res.data);
  },
  checkIn(id: number, location?: { lat: number; lng: number }): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/check-in`, location || {}).then((res) => res.data);
  },
  startExecuting(id: number): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/start-executing`).then((res) => res.data);
  },
  complete(id: number, data?: { note: string; attachments?: string[] }): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/complete`, data || {}).then((res) => res.data);
  },
};

// =====================
// 设备实时监控 API
// =====================
export const deviceMonitorApi = {
  getRealtimeMetrics(deviceIds?: number[]): Promise<ApiResponse<DeviceMetrics[]>> {
    return api.get('/monitor/realtime', { params: { deviceIds: deviceIds?.join(',') } }).then((res) => res.data);
  },
  getDeviceStatusList(params?: {
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/monitor/devices', { params }).then((res) => res.data);
  },
};

// =====================
// 设备巡检 API
// =====================
export const inspectionApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTask>>> {
    return api.get('/inspections', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<InspectionTask>> {
    return api.get(`/inspections/${id}`).then((res) => res.data);
  },
  create(data: Partial<InspectionTask>): Promise<ApiResponse<InspectionTask>> {
    return api.post('/inspections', data).then((res) => res.data);
  },
  start(id: number): Promise<ApiResponse<InspectionTask>> {
    return api.post(`/inspections/${id}/start`).then((res) => res.data);
  },
  updateItem(
    taskId: number,
    itemId: number,
    data: { result: string; note?: string }
  ): Promise<ApiResponse<InspectionTask>> {
    return api.patch(`/inspections/${taskId}/items/${itemId}`, data).then((res) => res.data);
  },
  complete(id: number, data: { summary: string; overall: string }): Promise<ApiResponse<InspectionTask>> {
    return api.post(`/inspections/${id}/complete`, data).then((res) => res.data);
  },
};

// =====================
// 数据看板 API
// =====================
export const dashboardApi = {
  getDashboard(): Promise<ApiResponse<DashboardData>> {
    return api.get('/dashboard').then((res) => res.data);
  },
  getAlarmTrends(params?: {
    days?: number;
  }): Promise<ApiResponse<AlarmTrend[]>> {
    return api.get('/dashboard/alarm-trends', { params }).then((res) => res.data);
  },
  getWorkOrderTrends(params?: {
    days?: number;
  }): Promise<ApiResponse<WorkOrderTrend[]>> {
    return api.get('/dashboard/workorder-trends', { params }).then((res) => res.data);
  },
  getDeviceHealth(): Promise<ApiResponse<DeviceHealthStats>> {
    return api.get('/dashboard/device-health').then((res) => res.data);
  },
};

// =====================
// 工单流转 API
// =====================
export const workOrderTransferApi = {
  transfer(id: number, data: { assigneeId: number; reason: string }): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/transfer`, data).then((res) => res.data);
  },
  escalate(id: number, reason: string): Promise<ApiResponse<WorkOrder>> {
    return api.post(`/work-orders/${id}/escalate`, { reason }).then((res) => res.data);
  },
};

export default api;