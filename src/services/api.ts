import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  WorkOrder,
  Alarm,
  Device,
  DeviceMetrics,
  DeviceHealth,
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
  EnergyTrendItem,
  ReportSummary,
  UserDetail,
  AuthMe,
  DeviceReport,
  AlarmReport,
  Role,
  Permission,
  AlarmRule,
  NotificationRule,
  NotificationTemplate,
  WorkOrderReport,
  SparePart,
  ChargerConfig,
  PricingRule,
  EfficiencyReport,
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
  /** GET /devices/{id}/health — 设备健康度 */
  getHealth(id: number): Promise<ApiResponse<DeviceHealth>> {
    return api.get(`/devices/${id}/health`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          deviceId: (d.device_id as number) ?? 0,
          deviceCode: (d.device_code as string) ?? '',
          deviceName: (d.device_name as string) ?? '',
          deviceType: (d.device_type as string) ?? '',
          healthScore: (d.health_score as number) ?? 0,
          healthStatus: (d.health_status as string) ?? '',
          healthStatusDisplay: (d.health_status_display as string) ?? '',
          dimensionScores: (d.dimension_scores as Record<string, number>) ?? {},
          checkedAt: (d.checked_at as string) ?? '',
          lastHealthCheck: (d.last_health_check as string | null) ?? null,
        },
      };
    });
  },
  /** GET /devices/{id}/config — 充电桩设备配置 */
  getConfig(id: number): Promise<ApiResponse<ChargerConfig>> {
    return api.get(`/devices/${id}/config`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          deviceId: (d.device_id as number) ?? 0,
          voltageLimit: (d.voltage_limit as number) ?? 0,
          currentLimit: (d.current_limit as number) ?? 0,
          maxPower: (d.max_power as number) ?? 0,
          chargeMode: (d.charge_mode as string) ?? '',
          overloadProtection: (d.overload_protection as boolean) ?? false,
          timePeriods: ((d.time_periods as { start_time: string; end_time: string; power_limit: number }[]) ?? []).map((tp) => ({
            startTime: tp.start_time,
            endTime: tp.end_time,
            powerLimit: tp.power_limit,
          })),
          createdAt: (d.created_at as string | null) ?? null,
          updatedAt: (d.updated_at as string | null) ?? null,
        },
      };
    });
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

// =====================
// 角色管理 API (GET /roles)
// =====================
export const roleApi = {
  /** GET /roles — 角色列表 */
  getList(): Promise<ApiResponse<Role[]>> {
    return api.get('/roles').then((res) => {
      const raw = res.data as ApiResponse<{ items?: Record<string, unknown>[] }>;
      const items = (raw.data?.items ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        })),
      };
    });
  },
};

// =====================
// 权限管理 API (GET /permissions)
// =====================
export const permissionApi = {
  /** GET /permissions — 权限列表 */
  getList(): Promise<ApiResponse<Permission[]>> {
    return api.get('/permissions').then((res) => {
      const raw = res.data as ApiResponse<{ items?: Record<string, unknown>[] }>;
      const items = (raw.data?.items ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          name: (it.name as string) ?? '',
          resource: (it.resource as string) ?? '',
          action: (it.action as string) ?? '',
          label: (it.label as string) ?? '',
          labelShort: (it.label_short as string) ?? '',
        })),
      };
    });
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

  /** GET /energy/trend — 31天光伏充电趋势 */
  getTrend(): Promise<ApiResponse<EnergyTrendItem[]>> {
    return api.get('/energy/trend').then((res) => {
      const raw = res.data as ApiResponse<{ trend?: Record<string, unknown>[] }>;
      const items = (raw.data?.trend ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((d) => ({
          date: (d.date as string) ?? '',
          pvGeneration: (d.pv_generation as number) ?? 0,
          chargingAmount: (d.charging_amount as number) ?? 0,
          dischargeAmount: (d.discharge_amount as number) ?? 0,
          pvRevenue: (d.pv_revenue as number) ?? 0,
          chargingRevenue: (d.charging_revenue as number) ?? 0,
          dischargeRevenue: (d.discharge_revenue as number) ?? 0,
          totalRevenue: (d.total_revenue as number) ?? 0,
        })),
      };
    });
  },
};

// =====================
// 用户管理 API
// =====================
export const userApi = {
  /** GET /users/{id} — 用户详情 */
  getDetail(id: number): Promise<ApiResponse<UserDetail>> {
    return api.get(`/users/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          username: (d.username as string) ?? '',
          realName: (d.real_name as string) ?? '',
          phone: (d.phone as string | null) ?? null,
          role: (d.role as string) ?? '',
          level: (d.level as string) ?? '',
          teamId: (d.team_id as number | null) ?? null,
          teamName: (d.team_name as string | null) ?? null,
          status: (d.status as string) ?? '',
          lastLogin: (d.last_login as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
          updatedAt: (d.updated_at as string) ?? '',
        },
      };
    });
  },
};

// =====================
// 报告 API (GET /reports/summary)
// =====================
export const reportApi = {
  /** GET /reports/summary — 30天运维报告概览 */
  getSummary(): Promise<ApiResponse<ReportSummary>> {
    return api.get('/reports/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const overview = (d.overview ?? {}) as Record<string, unknown>;
      const health = (d.station_health ?? {}) as Record<string, unknown>;
      const dist = (health.distribution ?? {}) as Record<string, unknown>;
      const team = (d.team_performance ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          overview: {
            totalDevices: (overview.total_devices as number) ?? 0,
            onlineDevices: (overview.online_devices as number) ?? 0,
            offlineDevices: (overview.offline_devices as number) ?? 0,
            faultDevices: (overview.fault_devices as number) ?? 0,
            maintenanceDevices: (overview.maintenance_devices as number) ?? 0,
            onlineRate: (overview.online_rate as number) ?? 0,
            totalStations: (overview.total_stations as number) ?? 0,
            totalWorkorders: (overview.total_workorders as number) ?? 0,
            completedWorkorders: (overview.completed_workorders as number) ?? 0,
            completionRate: (overview.completion_rate as number) ?? 0,
            totalAlarms: (overview.total_alarms as number) ?? 0,
            activeAlarms: (overview.active_alarms as number) ?? 0,
          },
          stationHealth: {
            distribution: {
              normal: (dist.normal as number) ?? 0,
              warning: (dist.warning as number) ?? 0,
              critical: (dist.critical as number) ?? 0,
              offline: (dist.offline as number) ?? 0,
            },
            healthyRate: (health.healthy_rate as number) ?? 0,
          },
          teamPerformance: {
            engineers: (team.engineers as unknown[]) ?? [],
            totalEngineers: (team.total_engineers as number) ?? 0,
            topEngineers: (team.top_engineers as unknown[]) ?? [],
          },
        },
      };
    });
  },

  /** GET /reports/devices — 30天设备报告 */
  getDeviceReport(): Promise<ApiResponse<DeviceReport>> {
    return api.get('/reports/devices').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalDevices: (d.total_devices as number) ?? 0,
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          stationDistribution: ((d.station_distribution as Record<string, unknown>[]) ?? []).map((s) => ({
            stationId: (s.station_id as number) ?? 0,
            stationName: (s.station_name as string) ?? '',
            deviceCount: (s.device_count as number) ?? 0,
          })),
        },
      };
    });
  },

  /** GET /reports/alarms — 30天告警报告 */
  getAlarmReport(): Promise<ApiResponse<AlarmReport>> {
    return api.get('/reports/alarms').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalAlarms: (d.total_alarms as number) ?? 0,
          levelDistribution: (d.level_distribution as Record<string, number>) ?? {},
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          resolvedRate: (d.resolved_rate as number) ?? 0,
          activeAlarms: (d.active_alarms as number) ?? 0,
          topFaultDevices: ((d.top_fault_devices as Record<string, unknown>[]) ?? []).map((t) => ({
            deviceId: (t.device_id as number) ?? 0,
            deviceName: (t.device_name as string) ?? '',
            alarmCount: (t.alarm_count as number) ?? 0,
          })),
          dailyTrend: ((d.daily_trend as Record<string, unknown>[]) ?? []).map((t) => ({
            date: (t.date as string) ?? '',
            count: (t.count as number) ?? 0,
          })),
        },
      };
    });
  },

  /** GET /reports/workorders — 30天工单报告 */
  getWorkOrderReport(): Promise<ApiResponse<WorkOrderReport>> {
    return api.get('/reports/workorders').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const eff = (d.efficiency ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalWorkorders: (d.total_workorders as number) ?? 0,
          typeDistribution: (d.type_distribution as Record<string, number>) ?? {},
          levelDistribution: (d.level_distribution as Record<string, number>) ?? {},
          statusDistribution: (d.status_distribution as Record<string, number>) ?? {},
          completionRate: (d.completion_rate as number) ?? 0,
          efficiency: {
            avgResponseHours: (eff.avg_response_hours as number) ?? 0,
            avgCompletionHours: (eff.avg_completion_hours as number) ?? 0,
          },
          engineerPerformance: ((d.engineer_performance as Record<string, unknown>[]) ?? []).map((e) => ({
            engineerId: (e.engineer_id as number) ?? 0,
            engineerName: (e.engineer_name as string) ?? '',
            completedCount: (e.completed_count as number) ?? 0,
            avgCompletionHours: (e.avg_completion_hours as number) ?? 0,
          })),
        },
      };
    });
  },

  /** GET /reports/efficiency — 效率报告 */
  getEfficiency(params?: {
    period?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<EfficiencyReport>> {
    return api.get('/reports/efficiency', { params: { period: params?.period, page: params?.page, page_size: params?.pageSize } }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const alerts = (d.alerts ?? {}) as Record<string, unknown>;
      const abnormal = (alerts.abnormal_low_efficiency ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          items: ((d.items as Record<string, unknown>[]) ?? []).map((item) => ({
            stationId: (item.station_id as number) ?? undefined,
            stationName: (item.station_name as string) ?? undefined,
            deviceId: (item.device_id as number) ?? undefined,
            deviceName: (item.device_name as string) ?? undefined,
            efficiency: (item.efficiency as number) ?? undefined,
            uptime: (item.uptime as number) ?? undefined,
            utilization: (item.utilization as number) ?? undefined,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
          alerts: {
            abnormalLowEfficiency: {
              count: (abnormal.count as number) ?? 0,
              threshold: (abnormal.threshold as string) ?? '',
              items: ((abnormal.items as Record<string, unknown>[]) ?? []).map((item) => ({
                stationId: (item.station_id as number) ?? undefined,
                stationName: (item.station_name as string) ?? undefined,
                deviceId: (item.device_id as number) ?? undefined,
                deviceName: (item.device_name as string) ?? undefined,
                efficiency: (item.efficiency as number) ?? undefined,
                uptime: (item.uptime as number) ?? undefined,
                utilization: (item.utilization as number) ?? undefined,
              })),
            },
          },
        },
      };
    });
  },
};

// =====================
// 告警规则 API (GET /alarm-rules)
// =====================
export const alarmRuleApi = {
  /** GET /alarm-rules — 告警规则列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<AlarmRule>>> {
    return api.get('/alarm-rules', { params: { page: params?.page, page_size: params?.pageSize } }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
        id: (it.id as number) ?? 0,
        name: (it.name as string) ?? '',
        deviceType: (it.device_type as string) ?? '',
        metric: (it.metric as string) ?? '',
        condition: (it.condition as string) ?? '',
        threshold: (it.threshold as number) ?? 0,
        level: ((it.level as string) ?? 'warning') as AlarmRule['level'],
        enabled: (it.enabled as boolean) ?? false,
        description: (it.description as string) ?? '',
        createdAt: (it.created_at as string) ?? '',
        updatedAt: (it.updated_at as string) ?? '',
      }));
      return {
        ...raw,
        data: {
          items,
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? params?.page ?? 1,
          pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
        },
      };
    });
  },
};

// =====================
// 通知规则 API (GET /notification-rules)
// =====================
export const notificationRuleApi = {
  /** GET /notification-rules — 通知规则列表 */
  getList(): Promise<ApiResponse<NotificationRule[]>> {
    return api.get('/notification-rules').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[] | unknown>;
      const items = (Array.isArray(raw.data) ? raw.data : []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          event: (it.event as string) ?? '',
          channels: (it.channels as string[]) ?? [],
          recipients: (it.recipients as string[]) ?? [],
          enabled: (it.enabled as boolean) ?? false,
          template: (it.template as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        })),
      };
    });
  },
};

// =====================
// 备件 API (GET /spare-parts)
// =====================
export const sparePartApi = {
  /** GET /spare-parts — 备件列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<SparePart>>> {
    return api
      .get('/spare-parts', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          model: (it.model as string) ?? '',
          manufacturer: (it.manufacturer as string) ?? '',
          stockQty: (it.stock_qty as number) ?? 0,
          unit: (it.unit as string) ?? '',
          price: (it.price as number) ?? 0,
          warehouse: (it.warehouse as string) ?? '',
          location: (it.location as string) ?? '',
          safetyStock: (it.safety_stock as number) ?? 0,
          status: (it.status as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },
};

// =====================
// 通知模板 API (GET /notifications/templates)
// =====================
export const notificationTemplateApi = {
  /** GET /notifications/templates — 通知模板列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<NotificationTemplate>>> {
    return api
      .get('/notifications/templates', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          channel: (it.channel as string) ?? '',
          subject: (it.subject as string) ?? '',
          body: (it.body as string) ?? '',
          variables: (it.variables as string[]) ?? [],
          enabled: (it.enabled as boolean) ?? false,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },
};

// =====================
// 定价规则 API (/pricing)
// =====================
export const pricingApi = {
  /** GET /pricing — 定价规则列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<PricingRule>>> {
    return api
      .get('/pricing', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          periodType: (it.period_type as string) ?? '',
          startTime: (it.start_time as string) ?? '',
          endTime: (it.end_time as string) ?? '',
          energyPrice: it.energy_price as number | undefined,
          servicePrice: it.service_price as number | undefined,
          powerLimit: it.power_limit as number | undefined,
          enabled: (it.enabled as boolean) ?? false,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },

  /** GET /pricing/{id} — 定价规则详情 */
  getById(id: number): Promise<ApiResponse<PricingRule | null>> {
    return api.get(`/pricing/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown> | null>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: raw.data
          ? {
              id: (it.id as number) ?? 0,
              name: (it.name as string) ?? '',
              periodType: (it.period_type as string) ?? '',
              startTime: (it.start_time as string) ?? '',
              endTime: (it.end_time as string) ?? '',
              energyPrice: it.energy_price as number | undefined,
              servicePrice: it.service_price as number | undefined,
              powerLimit: it.power_limit as number | undefined,
              enabled: (it.enabled as boolean) ?? false,
              createdAt: (it.created_at as string) ?? '',
              updatedAt: (it.updated_at as string) ?? '',
            }
          : null,
      };
    });
  },
};