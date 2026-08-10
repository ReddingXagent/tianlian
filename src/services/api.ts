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
  EnergySummary,
} from '../types';

const TOKEN_KEY = 'auth_token';
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? 'http://localhost:8000/api/v1' : 'http://8.134.106.166/api/v1');

// eslint-disable-next-line import/no-named-as-default-member
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
// 工单契约映射（后端 snake_case ↔ 前端 camelCase）
// =====================
export const WO_LEVEL_TO_PRIORITY: Record<string, 'low' | 'normal' | 'high' | 'urgent'> = {
  info: 'low',
  warning: 'normal',
  critical: 'high',
  fatal: 'urgent',
};
export const WO_PRIORITY_TO_LEVEL: Record<string, string> = {
  low: 'info',
  normal: 'warning',
  high: 'critical',
  urgent: 'critical',
};
export const WO_BACKEND_STATUS_TO_CLIENT: Record<string, 'pending' | 'in_progress' | 'completed' | 'cancelled'> = {
  pending: 'pending',
  accepted: 'in_progress',
  processing: 'in_progress',
  pending_verify: 'completed',
  completed: 'completed',
};
export const WO_CLIENT_STATUS_TO_BACKEND: Record<string, string> = {
  pending: 'pending',
  in_progress: 'processing',
  completed: 'completed',
};

 
interface RawWorkOrder {
  id?: string | number;
  station_id?: number;
  station_name?: string;
  fault_desc?: string;
  type?: string;
  level?: string;
  status?: string;
  assignee_id?: number;
  assignee_name?: string;
  creator_id?: number;
  creator_name?: string;
  finish_time?: string;
  create_time?: string;
  update_time?: string;
  solution?: string;
}

interface RawRecord {
  id?: string | number;
  action?: string;
  description?: string;
  created_at?: string;
}

export function mapWorkOrder(raw: RawWorkOrder): WorkOrder {
  return {
    id: String(raw.id),
    stationId: raw.station_id ?? 0,
    stationName: raw.station_name ?? '',
    title: raw.fault_desc ?? '',
    description: raw.fault_desc ?? '',
    type: (raw.type ?? 'repair') as WorkOrder['type'],
    priority: WO_LEVEL_TO_PRIORITY[raw.level ?? ''] ?? 'normal',
    status: WO_BACKEND_STATUS_TO_CLIENT[raw.status ?? ''] ?? 'pending',
    assigneeId: raw.assignee_id ?? undefined,
    assigneeName: raw.assignee_name ?? undefined,
    creatorId: raw.creator_id ?? 999,
    creatorName: raw.creator_name ?? '',
    completedAt: raw.finish_time ?? undefined,
    createdAt: raw.create_time ?? '',
    updatedAt: raw.update_time ?? raw.create_time ?? '',
    solution: raw.solution ?? undefined,
  };
}

// =====================
// 工单 API（对齐后端真契约: /work-orders, id=WO-字符串）
// =====================
export const workOrderApi = {
  getList(params?: {
    status?: string;
    level?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    const query: Record<string, unknown> = {
      page: params?.page,
      page_size: params?.pageSize,
      level: params?.level,
      type: params?.type,
    };
    if (params?.status) {
      query.status = WO_CLIENT_STATUS_TO_BACKEND[params.status] ?? params.status;
    }
    return api.get('/work-orders', { params: query }).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
       
      const rawPage = (env.data ?? {}) as Record<string, unknown>;
      return {
        ...env,
        data: {
           
          items: ((rawPage.items as RawWorkOrder[]) ?? []).map((it) => mapWorkOrder(it)),
          total: (rawPage.total as number) ?? 0,
          page: (rawPage.page as number) ?? params?.page ?? 1,
          pageSize: (rawPage.page_size as number) ?? params?.pageSize ?? 20,
        },
      };
    });
  },
  getDetail(id: string): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => ({
      ...res.data,
      data: mapWorkOrder(res.data.data),
    }));
  },
  create(data: {
    faultDesc: string;
    type?: string;
    level?: string;
    stationId?: number;
    deviceId?: number;
  }): Promise<ApiResponse<WorkOrder>> {
    return api
      .post('/work-orders', {
        fault_desc: data.faultDesc,
        type: data.type ?? 'repair',
        level: data.level ?? 'warning',
        station_id: data.stationId,
        device_id: data.deviceId,
      })
      .then((res) => ({ ...res.data, data: mapWorkOrder(res.data.data) }));
  },
  update(
    id: string,
    data: { faultDesc?: string; level?: string; status?: string; assigneeId?: number; solution?: string }
  ): Promise<ApiResponse<WorkOrder>> {
    return api
      .put(`/work-orders/${id}`, {
        fault_desc: data.faultDesc,
        level: data.level,
        status: data.status ? WO_CLIENT_STATUS_TO_BACKEND[data.status] ?? data.status : undefined,
        assignee_id: data.assigneeId,
        solution: data.solution,
      })
      .then((res) => ({ ...res.data, data: mapWorkOrder(res.data.data) }));
  },
  updateStatus(id: string, status: string): Promise<ApiResponse<WorkOrder>> {
    const backendStatus = WO_CLIENT_STATUS_TO_BACKEND[status];
    if (!backendStatus) {
      return Promise.reject(new Error(`后端不支持的工单状态: ${status}`));
    }
    return workOrderApi.update(id, { status: backendStatus });
  },
  assign(id: string, assigneeId: number): Promise<ApiResponse<WorkOrder>> {
    return workOrderApi.update(id, { assigneeId });
  },
  dispatch(id: string, auto = true): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/dispatch`, { auto }).then((res) => res.data);
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
// 工单执行记录 API（后端: GET /logs + POST /notes）
// =====================
export const workOrderRecordApi = {
  getRecords(orderId: string): Promise<ApiResponse<WorkOrderRecord[]>> {
    return api.get(`/work-orders/${orderId}/logs`).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
       
      const items = ((env.data as Record<string, unknown>)?.items as RawRecord[]) ?? [];
      return {
        ...env,
        data: items.map((it) => ({
          id: Number(it.id ?? 0),
          orderId,
          action: (it.action ?? 'executing') as WorkOrderRecord['action'],
          operatorId: 0,
          operatorName: '系统',
          note: it.description ?? '',
          createdAt: it.created_at ?? '',
        })),
      };
    });
  },
  addRecord(orderId: string, data: { action: string; note: string }): Promise<ApiResponse<WorkOrderRecord>> {
    return api.post(`/work-orders/${orderId}/notes`, data).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
       
      const it = (env.data ?? {}) as Record<string, unknown>;
      return {
        ...env,
        data: {
          id: Number(it.id ?? 0),
          orderId,
          action: (String(it.action ?? data.action)) as WorkOrderRecord['action'],
          operatorId: 0,
          operatorName: '手工记录',
          note: String(it.description ?? data.note),
          createdAt: String(it.created_at ?? ''),
        },
      };
    });
  },
};

// =====================
// 工单操作 API（后端真端点: accept/start/complete/verify）
// =====================
export const workOrderActionApi = {
  accept(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/accept`).then((res) => res.data);
  },
  start(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/start`).then((res) => res.data);
  },
  complete(id: string, solution?: string): Promise<ApiResponse<unknown>> {
    return api
      .post(`/work-orders/${id}/complete`, null, { params: solution ? { solution } : {} })
      .then((res) => res.data);
  },
  verify(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/verify`).then((res) => res.data);
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
// 工单流转 API（后端真端点: transfer / urge催单）
// =====================
export const workOrderTransferApi = {
  transfer(id: string, data: { targetEngineerId: number; reason: string }): Promise<ApiResponse<unknown>> {
    return api
      .post(`/work-orders/${id}/transfer`, {
        target_engineer_id: data.targetEngineerId,
        reason: data.reason,
      })
      .then((res) => res.data);
  },
  urge(id: string, message = '请尽快处理'): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/urge`, { message }).then((res) => res.data);
  },
};

export default api;

// =====================
// 能源概览 API (GET /energy/summary)
// =====================
export const energyApi = {
  getSummary(): Promise<ApiResponse<EnergySummary>> {
    return api.get('/energy/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const yoy = (d.yoy ?? {}) as Record<string, unknown>;
      const price = (d.price_info ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          period: (d.period as string) ?? 'month',
          days: (d.days as number) ?? 0,
          pvGeneration: (d.pv_generation as number) ?? 0,
          chargingAmount: (d.charging_amount as number) ?? 0,
          dischargeAmount: (d.discharge_amount as number) ?? 0,
          pvRevenue: (d.pv_revenue as number) ?? 0,
          chargingRevenue: (d.charging_revenue as number) ?? 0,
          dischargeRevenue: (d.discharge_revenue as number) ?? 0,
          totalRevenue: (d.total_revenue as number) ?? 0,
          yoy: {
            pvGenerationYoy: (yoy.pv_generation_yoy as number) ?? 0,
            chargingAmountYoy: (yoy.charging_amount_yoy as number) ?? 0,
            dischargeAmountYoy: (yoy.discharge_amount_yoy as number) ?? 0,
            totalRevenueYoy: (yoy.total_revenue_yoy as number) ?? 0,
          },
          priceInfo: {
            feedInTariff: (price.feed_in_tariff as number) ?? 0,
            chargingPrice: (price.charging_price as number) ?? 0,
            dischargePrice: (price.discharge_price as number) ?? 0,
          },
        },
      };
    });
  },
};