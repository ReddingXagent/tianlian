import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  ApiResponse,
  LoginRequest,
  LoginResponse,
  RefreshTokenResponse,
  WorkOrder,
  Alarm,
  Device,
  DeviceMetrics,
  DeviceHealth,
  DeviceHealthHistory,
  MonitorSummary,
  ScanResult,
  PaginatedData,
  WorkbenchStats,
  DiagnosisResult,
  WorkOrderRecord,
  InspectionTask,
  InspectionPlan,
  InspectionTemplate,
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
  PermissionTreeNode,
  AlarmRule,
  NotificationRule,
  NotificationTemplate,
  NotificationStats,
  WorkOrderReport,
  SparePart,
  SparePartCreate,
  ChargerConfig,
  PricingRule,
  EfficiencyReport,
  Engineer,
  Webhook,
  HealingRule,
  HealingRuleCreate,
  HealingExecution,
  HealingStats,
  ApiKey,
  SecurityLog,
  SecurityPolicy,
  SecurityThreat,
  DeviceHealthRanking,
  WorkOrderStats,
  RevenueAnalytics,
  KnowledgeArticleItem,
  KnowledgeFaqItem,
  KnowledgeCategoryItem,
  UnreadCount,
  ReadAllResult,
  RealtimeOverview,
  Gateway,
  GatewayStatus,
  GatewayFirmware,
  Tenant,
  ChatSource,
  ChatAction,
  ChatResponse,
  NotificationSendResult,
  VppResource,
  VppResourceType,
  VppDispatchMode,
  VppDispatchCommand,
  VppDispatchPlan,
  VppDispatchHistory,
  FleetDriver,
  Team,
  TeamUpdate,
  TeamCreate,
  RunbookTemplateSummary,
  RunbookTemplateDetail,
  HealthStatus,
  SystemHealth,
  LivenessProbe,
  Station,
  StationBranding,
  ChargingOrder,
} from '../types';

/** health端点返回类型 */
export type HealthInfo = {
  status: HealthStatus;
  version: string;
  service: string;
};

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
  getStats(): Promise<ApiResponse<WorkOrderStats>> {
    return api.get('/work-orders/stats').then((res) => ({
      ...res.data,
      data: {
        total: res.data.data?.total ?? 0,
        statusDistribution: res.data.data?.status_distribution ?? {},
        levelDistribution: res.data.data?.level_distribution ?? {},
        typeDistribution: res.data.data?.type_distribution ?? {},
        groups: res.data.data?.groups ?? {},
      },
    }));
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
  /** PUT /alarms/{id}/resolve — 解决告警 */
  resolve(id: number): Promise<ApiResponse<Alarm>> {
    return api.put(`/alarms/${id}/resolve`).then((res) => res.data);
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
  /** GET /devices/health — 全局设备健康列表 */
  getHealthList(params?: {
    status?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<DeviceHealthSummary>>> {
    return api.get('/devices/health', { params }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((item) => ({
        id: (item.id as number) ?? 0,
        code: (item.code as string) ?? '',
        name: (item.name as string) ?? '',
        type: (item.type as string) ?? '',
        healthScore: (item.health_score as number) ?? 0,
        status: (item.status as string) ?? '',
      }));
      return {
        ...raw,
        data: {
          items,
          total: (d.total as number) ?? items.length,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? items.length,
        },
      };
    });
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
  /** GET /devices/{id}/health/history — 设备健康历史记录 */
  getHealthHistory(id: number): Promise<ApiResponse<DeviceHealthHistory[]>> {
    return api.get(`/devices/${id}/health/history`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[]>;
      const items = ((raw.data ?? []) as Record<string, unknown>[]).map((d) => ({
        deviceId: (d.device_id as number) ?? id,
        healthScore: (d.health_score as number) ?? 0,
        healthStatus: (d.health_status as string) ?? '',
        healthStatusDisplay: (d.health_status_display as string) ?? '',
        dimensionScores: (d.dimension_scores as Record<string, number>) ?? {},
        checkedAt: (d.checked_at as string) ?? (d.created_at as string) ?? '',
      }));
      return { ...raw, data: items };
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
// 知识库 API (knowledge — /knowledge/articles, /knowledge/categories, /knowledge/search)
// =====================
export const knowledgeApi = {
  /** GET /knowledge/articles — 知识库文章列表 */
  getArticles(params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<KnowledgeArticleItem>>> {
    const query = params ? `?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` : '';
    return api
      .get(`/knowledge/articles${query}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          title: (it.title as string) ?? '',
          content: (it.content as string) ?? '',
          summary: (it.summary as string) ?? '',
          categoryId: (it.category_id as number) ?? 0,
          categoryName: (it.category_name as string) ?? undefined,
          tags: ((it.tags as string[]) ?? []),
          author: (it.author as string) ?? '',
          viewCount: (it.view_count as number) ?? 0,
          status: (it.status as 'published' | 'draft' | 'archived') ?? 'draft',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? 1,
            pageSize: (d.page_size as number) ?? 20,
          },
        };
      });
  },

  /** GET /knowledge/faq — 知识库FAQ列表 */
  getFaq(): Promise<ApiResponse<KnowledgeFaqItem[]>> {
    return api
      .get('/knowledge/faq')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>[] | Record<string, unknown>>;
        const items = (Array.isArray(raw.data) ? raw.data : (raw.data as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
        const mapped = items.map((it) => ({
          id: (it.id as number) ?? 0,
          question: (it.question as string) ?? '',
          answer: (it.answer as string) ?? '',
          categoryId: (it.category_id as number) ?? undefined,
          sortOrder: (it.sort_order as number) ?? undefined,
        }));
        return { ...raw, data: mapped };
      });
  },

  /** GET /knowledge/categories — 知识库分类列表 */
  getCategories(): Promise<ApiResponse<KnowledgeCategoryItem[]>> {
    return api
      .get('/knowledge/categories')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>[] | Record<string, unknown>>;
        const items = (Array.isArray(raw.data) ? raw.data : (raw.data as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
        const mapped = items.map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          description: (it.description as string) ?? '',
          articleCount: (it.article_count as number) ?? 0,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return { ...raw, data: mapped };
      });
  },

  /** GET /knowledge/search?q=keyword — 知识库搜索 */
  search(keyword: string, params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<KnowledgeArticleItem>>> {
    const page = params?.page ?? 1;
    const pageSize = params?.page_size ?? 20;
    return api
      .get(`/knowledge/search?q=${encodeURIComponent(keyword)}&page=${page}&page_size=${pageSize}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          title: (it.title as string) ?? '',
          content: (it.content as string) ?? '',
          summary: (it.summary as string) ?? '',
          categoryId: (it.category_id as number) ?? 0,
          categoryName: (it.category_name as string) ?? undefined,
          tags: ((it.tags as string[]) ?? []),
          author: (it.author as string) ?? '',
          viewCount: (it.view_count as number) ?? 0,
          status: (it.status as 'published' | 'draft' | 'archived') ?? 'draft',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? 1,
            pageSize: (d.page_size as number) ?? 20,
          },
        };
      });
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
  /** GET /monitor/realtime — 实时监控总览 (含设备列表) */
  getRealtimeOverview(): Promise<ApiResponse<RealtimeOverview>> {
    return api.get('/monitor/realtime').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          totalPower: (d.totalPower as number) ?? 0,
          powerTrend: (d.powerTrend as number) ?? 0,
          todayGeneration: (d.todayGeneration as number) ?? 0,
          todayConsumption: (d.todayConsumption as number) ?? 0,
          gridImport: (d.gridImport as number) ?? 0,
          gridExport: (d.gridExport as number) ?? 0,
          efficiency: (d.efficiency as number) ?? 0,
          updateTime: (d.update_time as string) ?? '',
          devices: ((d.devices as Record<string, unknown>[]) ?? []).map((it) => ({
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            type: (it.type as string) ?? '',
            power: (it.power as number) ?? 0,
            status: (it.status as string) ?? '',
          })),
        } as RealtimeOverview,
      };
    });
  },
  /** @deprecated Use getRealtimeOverview() instead */
  getRealtimeMetrics(_deviceIds?: number[]): Promise<ApiResponse<DeviceMetrics[]>> {
    return Promise.resolve({ code: 200, message: 'deprecated', data: [] });
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

  /** GET /roles/{id} — 角色详情 (含完整权限列表) */
  getById(id: number): Promise<ApiResponse<Role>> {
    return api.get(`/roles/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        },
      };
    });
  },

  /** GET /roles/tree — 权限树 (按 resource 分组的层级结构) */
  getTree(): Promise<ApiResponse<PermissionTreeNode[]>> {
    return api.get('/roles/tree').then((res) => {
      const raw = res.data as ApiResponse<{ tree?: Record<string, unknown>[] }>;
      const items = (raw.data?.tree ?? []) as Record<string, unknown>[];
      const mapNode = (it: Record<string, unknown>): PermissionTreeNode => ({
        key: (it.key as string) ?? '',
        title: (it.title as string) ?? '',
        resource: (it.resource as string) ?? '',
        name: it.name as string | undefined,
        action: it.action as string | undefined,
        label: it.label as string | undefined,
        isLeaf: (it.is_leaf as boolean) ?? false,
        children: Array.isArray(it.children)
          ? (it.children as Record<string, unknown>[]).map(mapNode)
          : undefined,
      });
      return { ...raw, data: items.map(mapNode) };
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
          partName: (it.part_name as string) ?? '',
          partModel: (it.part_model as string | null) ?? null,
          totalQuantity: (it.total_quantity as number) ?? 0,
          availableQuantity: (it.available_quantity as number) ?? 0,
          warehouse: (it.warehouse as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
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

  /** GET /spare-parts/{id} — 备件详情 */
  getById(id: number): Promise<ApiResponse<SparePart>> {
    return api.get(`/spare-parts/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          partName: (d.part_name as string) ?? '',
          partModel: (d.part_model as string | null) ?? null,
          totalQuantity: (d.total_quantity as number) ?? 0,
          availableQuantity: (d.available_quantity as number) ?? 0,
          warehouse: (d.warehouse as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** POST /spare-parts — 创建备件 (登记入库) */
  create(body: SparePartCreate): Promise<ApiResponse<SparePart>> {
    return api.post('/spare-parts', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          partName: (d.part_name as string) ?? '',
          partModel: (d.part_model as string | null) ?? null,
          totalQuantity: (d.total_quantity as number) ?? 0,
          availableQuantity: (d.available_quantity as number) ?? 0,
          warehouse: (d.warehouse as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** DELETE /spare-parts/{id} — 删除备件 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/spare-parts/${id}`).then((res) => res.data);
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
// 充电订单 API (/charging-orders)
// =====================
export const chargingOrderApi = {
  /** GET /charging-orders — 充电订单列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
    stationId?: number;
    orderStatus?: string;
    paymentStatus?: string;
  }): Promise<ApiResponse<PaginatedData<ChargingOrder>>> {
    return api
      .get('/charging-orders', {
        params: {
          page: params?.page,
          page_size: params?.pageSize,
          station_id: params?.stationId,
          order_status: params?.orderStatus,
          payment_status: params?.paymentStatus,
        },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          orderNo: (it.order_no as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          deviceId: (it.device_id as number) ?? 0,
          userId: (it.user_id as number) ?? 0,
          userType: (it.user_type as string | null) ?? null,
          vehicleId: (it.vehicle_id as string | null) ?? null,
          plateNumber: (it.plate_number as string | null) ?? null,
          startTime: (it.start_time as string | null) ?? null,
          endTime: (it.end_time as string | null) ?? null,
          durationMinutes: (it.duration_minutes as number) ?? 0,
          startSoc: it.start_soc as number | null ?? null,
          endSoc: it.end_soc as number | null ?? null,
          startMeter: it.start_meter as number | null ?? null,
          endMeter: it.end_meter as number | null ?? null,
          stopReason: (it.stop_reason as string | null) ?? null,
          chargedKwh: (it.charged_kwh as number) ?? 0,
          electricityFee: (it.electricity_fee as number) ?? 0,
          serviceFee: (it.service_fee as number) ?? 0,
          parkingFee: (it.parking_fee as number) ?? 0,
          idlePenalty: (it.idle_penalty as number) ?? 0,
          reservationFee: (it.reservation_fee as number) ?? 0,
          totalAmount: (it.total_amount as number) ?? 0,
          discountAmount: (it.discount_amount as number) ?? 0,
          paidAmount: (it.paid_amount as number) ?? 0,
          paymentStatus: (it.payment_status as ChargingOrder['paymentStatus']) ?? 'unpaid',
          orderStatus: (it.order_status as ChargingOrder['orderStatus']) ?? 'pending',
          paymentMethod: (it.payment_method as string | null) ?? null,
          remark: (it.remark as string | null) ?? null,
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

  /** GET /charging-orders/{id} — 充电订单详情 */
  getById(id: number): Promise<ApiResponse<ChargingOrder | null>> {
    return api.get(`/charging-orders/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown> | null>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: raw.data
          ? {
              id: (it.id as number) ?? 0,
              orderNo: (it.order_no as string) ?? '',
              stationId: (it.station_id as number) ?? 0,
              deviceId: (it.device_id as number) ?? 0,
              userId: (it.user_id as number) ?? 0,
              userType: (it.user_type as string | null) ?? null,
              vehicleId: (it.vehicle_id as string | null) ?? null,
              plateNumber: (it.plate_number as string | null) ?? null,
              startTime: (it.start_time as string | null) ?? null,
              endTime: (it.end_time as string | null) ?? null,
              durationMinutes: (it.duration_minutes as number) ?? 0,
              startSoc: it.start_soc as number | null ?? null,
              endSoc: it.end_soc as number | null ?? null,
              startMeter: it.start_meter as number | null ?? null,
              endMeter: it.end_meter as number | null ?? null,
              stopReason: (it.stop_reason as string | null) ?? null,
              chargedKwh: (it.charged_kwh as number) ?? 0,
              electricityFee: (it.electricity_fee as number) ?? 0,
              serviceFee: (it.service_fee as number) ?? 0,
              parkingFee: (it.parking_fee as number) ?? 0,
              idlePenalty: (it.idle_penalty as number) ?? 0,
              reservationFee: (it.reservation_fee as number) ?? 0,
              totalAmount: (it.total_amount as number) ?? 0,
              discountAmount: (it.discount_amount as number) ?? 0,
              paidAmount: (it.paid_amount as number) ?? 0,
              paymentStatus: (it.payment_status as ChargingOrder['paymentStatus']) ?? 'unpaid',
              orderStatus: (it.order_status as ChargingOrder['orderStatus']) ?? 'pending',
              paymentMethod: (it.payment_method as string | null) ?? null,
              remark: (it.remark as string | null) ?? null,
              createdAt: (it.created_at as string) ?? '',
              updatedAt: (it.updated_at as string) ?? '',
            }
          : null,
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

// =====================
// 巡检计划 API (/inspection/plans)
// =====================
export const inspectionPlanApi = {
  /** GET /inspection/plans — 巡检计划列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionPlan>>> {
    return api
      .get('/inspection/plans', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          deviceId: it.device_id as number | undefined,
          deviceName: it.device_name as string | undefined,
          type: (it.type as InspectionPlan['type']) ?? 'daily',
          status: (it.status as InspectionPlan['status']) ?? 'pending',
          scheduledDate: (it.scheduled_date as string) ?? '',
          cycle: it.cycle as string | undefined,
          assignedTo: it.assigned_to as number | undefined,
          assignedName: it.assigned_name as string | undefined,
          templateId: it.template_id as number | undefined,
          description: it.description as string | undefined,
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
// 巡检模板 API (/inspection/templates)
// =====================
export const inspectionTemplateApi = {
  /** GET /inspection/templates — 巡检模板列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTemplate>>> {
    return api
      .get('/inspection/templates', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          type: (it.type as InspectionTemplate['type']) ?? 'daily',
          items: ((it.items as Record<string, unknown>[]) ?? []).map((item) => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            expected: (item.expected as string) ?? '',
            result: item.result as 'pass' | 'fail' | 'na' | undefined,
            note: item.note as string | undefined,
          })),
          description: it.description as string | undefined,
          enabled: (it.enabled as boolean) ?? true,
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
// 巡检任务 V2 API (/inspection/tasks)
// =====================
export const inspectionTaskApi = {
  /** GET /inspection/tasks — 巡检任务列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTask>>> {
    return api
      .get('/inspection/tasks', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          deviceId: (it.device_id as number) ?? 0,
          deviceName: (it.device_name as string) ?? '',
          type: (it.type as InspectionTask['type']) ?? 'daily',
          status: (it.status as InspectionTask['status']) ?? 'pending',
          scheduledDate: (it.scheduled_date as string) ?? '',
          completedDate: it.completed_date as string | undefined,
          assignedTo: it.assigned_to as number | undefined,
          assignedName: it.assigned_name as string | undefined,
          description: (it.description as string) ?? '',
          items: ((it.items as Record<string, unknown>[]) ?? []).map((item) => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            expected: (item.expected as string) ?? '',
            result: item.result as 'pass' | 'fail' | 'na' | undefined,
            note: item.note as string | undefined,
          })),
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        })) as InspectionTask[];
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
// 工程师 API (/engineers)
// =====================
export interface EngineerCreate {
  username: string;
  password: string;
  name: string;
  phone?: string;
  level?: 'junior' | 'senior' | 'expert';
  role?: string;
}

export const engineerApi = {
  /** GET /engineers — 工程师列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Engineer>>> {
    return api
      .get('/engineers', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          username: (it.username as string) ?? '',
          name: (it.name as string) ?? '',
          phone: (it.phone as string | null) ?? null,
          level: (it.level as Engineer['level']) ?? 'junior',
          teamId: (it.team_id as number | null) ?? null,
          status: (it.status as Engineer['status']) ?? 'active',
          role: (it.role as string) ?? '',
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

  /** POST /engineers — 创建工程师 */
  create(body: EngineerCreate): Promise<ApiResponse<Engineer>> {
    return api
      .post('/engineers', {
        username: body.username,
        password: body.password,
        name: body.name,
        ...(body.phone !== undefined && { phone: body.phone }),
        ...(body.level !== undefined && { level: body.level }),
        ...(body.role !== undefined && { role: body.role }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            username: (it.username as string) ?? '',
            name: (it.name as string) ?? '',
            phone: (it.phone as string | null) ?? null,
            level: (it.level as Engineer['level']) ?? 'junior',
            teamId: (it.team_id as number | null) ?? null,
            status: (it.status as Engineer['status']) ?? 'active',
            role: (it.role as string) ?? '',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /engineers/{id} — 删除工程师 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/engineers/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};

// =====================
// Webhook API (/webhooks)
// =====================
export interface WebhookCreate {
  name: string;
  url: string;
  events?: string[];
  secret?: string;
  description?: string;
  enabled?: boolean;
}

export const webhookApi = {
  /** GET /webhooks — Webhook列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Webhook>>> {
    return api
      .get('/webhooks', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          url: (it.url as string) ?? '',
          events: ((it.event_types as string[]) ?? (it.events as string[]) ?? []),
          secret: (it.secret as string | null) ?? null,
          enabled: (it.enabled as boolean) ?? false,
          lastTriggeredAt: (it.last_triggered_at as string | null) ?? null,
          lastResponseStatus: (it.last_response_status as number | null) ?? null,
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

  /** POST /webhooks — 创建Webhook */
  create(body: WebhookCreate): Promise<ApiResponse<Webhook>> {
    return api
      .post('/webhooks', {
        name: body.name,
        url: body.url,
        events: body.events ?? [],
        ...(body.secret !== undefined && { secret: body.secret }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            url: (it.url as string) ?? '',
            events: ((it.event_types as string[]) ?? (it.events as string[]) ?? []),
            secret: (it.secret as string | null) ?? null,
            enabled: (it.enabled as boolean) ?? false,
            lastTriggeredAt: (it.last_triggered_at as string | null) ?? null,
            lastResponseStatus: (it.last_response_status as number | null) ?? null,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /webhooks/{id} — 删除Webhook */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/webhooks/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};

// =====================
// 自愈规则 API (/healing/rules)
// =====================
export const healingRuleApi = {
  /** GET /healing/rules — 自愈规则列表 (返回数组) */
  getList(): Promise<ApiResponse<HealingRule[]>> {
    return api
      .get('/healing/rules')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const arr = (Array.isArray(raw.data) ? raw.data : []) as Record<string, unknown>[];
        return {
          ...raw,
          data: arr.map((it) => ({
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            description: (it.description as string) ?? '',
            alarmPattern: (it.alarm_pattern as Record<string, unknown>) ?? {},
            runbookTemplate: (it.runbook_template as string | null) ?? null,
            autoApprove: (it.auto_approve as boolean) ?? false,
            maxRetries: (it.max_retries as number) ?? 0,
            cooldownMinutes: (it.cooldown_minutes as number) ?? 0,
            priority: (it.priority as number) ?? 0,
            enabled: (it.enabled as boolean) ?? false,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          })),
        };
      });
  },

  /** GET /healing/rules/{id} — 自愈规则详情 */
  getById(id: number): Promise<ApiResponse<HealingRule>> {
    return api
      .get(`/healing/rules/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            description: (it.description as string) ?? '',
            alarmPattern: (it.alarm_pattern as Record<string, unknown>) ?? {},
            runbookTemplate: (it.runbook_template as string | null) ?? null,
            autoApprove: (it.auto_approve as boolean) ?? false,
            maxRetries: (it.max_retries as number) ?? 0,
            cooldownMinutes: (it.cooldown_minutes as number) ?? 0,
            priority: (it.priority as number) ?? 0,
            enabled: (it.enabled as boolean) ?? false,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** POST /healing/rules — 创建自愈规则 */
  create(body: HealingRuleCreate): Promise<ApiResponse<{ id: number; name: string; message: string }>> {
    return api
      .post('/healing/rules', {
        name: body.name,
        alarm_pattern: body.alarmPattern,
        description: body.description ?? '',
        runbook_template: body.runbookTemplate ?? null,
        auto_approve: body.autoApprove ?? false,
        max_retries: body.maxRetries ?? 1,
        cooldown_minutes: body.cooldownMinutes ?? 30,
        priority: body.priority ?? 0,
        enabled: body.enabled ?? true,
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            message: (d.message as string) ?? '',
          },
        };
      });
  },

  /** DELETE /healing/rules/{id} — 删除自愈规则 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/healing/rules/${id}`).then((res) => res.data);
  },
};

// =====================
// 自愈执行记录 API (/healing/executions)
// =====================
export const healingExecutionApi = {
  /** GET /healing/executions — 自愈执行记录列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<HealingExecution>>> {
    return api
      .get('/healing/executions', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          ruleId: (it.rule_id as number) ?? 0,
          ruleName: (it.rule_name as string) ?? '',
          deviceId: (it.device_id as number) ?? 0,
          deviceName: (it.device_name as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          triggeredAt: (it.triggered_at as string) ?? '',
          status: (it.status as string) ?? '',
          actionTaken: (it.action_taken as string) ?? '',
          result: (it.result as string | null) ?? null,
          duration: (it.duration as number) ?? 0,
          errorMessage: (it.error_message as string | null) ?? null,
          createdAt: (it.created_at as string) ?? '',
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

  /** GET /healing/executions/{id} — 自愈执行记录详情 */
  getById(id: number): Promise<ApiResponse<HealingExecution>> {
    return api
      .get(`/healing/executions/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            ruleId: (it.rule_id as number) ?? 0,
            ruleName: (it.rule_name as string) ?? '',
            deviceId: (it.device_id as number) ?? 0,
            deviceName: (it.device_name as string) ?? '',
            stationId: (it.station_id as number) ?? 0,
            stationName: (it.station_name as string) ?? '',
            triggeredAt: (it.triggered_at as string) ?? '',
            status: (it.status as string) ?? '',
            actionTaken: (it.action_taken as string) ?? '',
            result: (it.result as string | null) ?? null,
            duration: (it.duration as number) ?? 0,
            errorMessage: (it.error_message as string | null) ?? null,
            createdAt: (it.created_at as string) ?? '',
          },
        };
      });
  },

  /** POST /healing/executions/{id}/retry — 重试自愈执行 */
  retry(id: number): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/retry`)
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** POST /healing/executions/{id}/approve — 批准自愈执行 */
  approve(id: number): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/approve`)
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** POST /healing/executions/{id}/reject — 拒绝自愈执行 */
  reject(id: number, reason?: string): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/reject`, { reason })
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** GET /healing/stats — 自愈统计数据 */
  getStats(): Promise<ApiResponse<HealingStats>> {
    return api
      .get('/healing/stats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            total: (d.total as number) ?? 0,
            statusBreakdown: (d.status_breakdown as Record<string, number>) ?? {},
            successRate: (d.success_rate as number) ?? 0,
            averageDurationMs: (d.average_duration_ms as number) ?? 0,
            autoApproveRate: (d.auto_approve_rate as number) ?? 0,
            pendingApprovals: (d.pending_approvals as number) ?? 0,
          },
        };
      });
  },
};

// =====================
// API密钥 API (/api-keys)
// =====================
export const apiKeyApi = {
  /** GET /api-keys — API密钥列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<ApiKey>>> {
    return api
      .get('/api-keys', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          keyPrefix: (it.key_prefix as string) ?? '',
          permissions: ((it.permissions as string[]) ?? []),
          lastUsedAt: (it.last_used_at as string | null) ?? null,
          expiresAt: (it.expires_at as string | null) ?? null,
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
// 安全审计日志 API (/security/logs)
// =====================
export const securityLogApi = {
  /** GET /security/logs — 安全审计日志列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<SecurityLog>>> {
    return api
      .get('/security/logs', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          timestamp: (it.timestamp as string) ?? '',
          userId: (it.user_id as number) ?? 0,
          username: (it.username as string) ?? '',
          userRole: (it.user_role as string | null) ?? null,
          action: (it.action as string) ?? '',
          module: (it.module as string) ?? '',
          targetId: (it.target_id as string) ?? '',
          targetDesc: (it.target_desc as string) ?? '',
          detail: (it.detail as string | null) ?? null,
          oldValue: (it.old_value as string | null) ?? null,
          newValue: (it.new_value as string | null) ?? null,
          ipAddress: (it.ip_address as string | null) ?? null,
          userAgent: (it.user_agent as string | null) ?? null,
          result: (it.result as 'success' | 'failure') ?? 'success',
          errorMsg: (it.error_msg as string | null) ?? null,
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
// 安全策略 API (/security/policies)
// =====================
export const securityPolicyApi = {
  /** GET /security/policies — 安全策略列表 */
  getList(): Promise<ApiResponse<PaginatedData<SecurityPolicy>>> {
    return api
      .get('/security/policies')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          policyKey: (it.policy_key as string) ?? '',
          policyConfig: (it.policy_config as Record<string, unknown>) ?? {},
          description: (it.description as string) ?? '',
          status: (it.status as 'active' | 'inactive') ?? 'active',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: 1,
            pageSize: items.length,
          },
        };
      });
  },

  /** GET /security/policies/{key} — 单个安全策略详情 */
  getByKey(key: string): Promise<ApiResponse<SecurityPolicy>> {
    return api
      .get(`/security/policies/${key}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            policyKey: (it.policy_key as string) ?? '',
            policyConfig: (it.policy_config as Record<string, unknown>) ?? {},
            description: (it.description as string) ?? '',
            status: (it.status as 'active' | 'inactive') ?? 'active',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },
};

/**
 * 营收分析 API — /analytics/revenue
 * 支持可选查询参数: start_date, end_date, period, station_id
 */
export const analyticsRevenueApi = {
  /** GET /analytics/revenue — 营收分析汇总 */
  getSummary(params?: {
    startDate?: string;
    endDate?: string;
    period?: string;
    stationId?: number;
  }): Promise<ApiResponse<RevenueAnalytics>> {
    const query: Record<string, string> = {};
    if (params?.startDate) query.start_date = params.startDate;
    if (params?.endDate) query.end_date = params.endDate;
    if (params?.period) query.period = params.period;
    if (params?.stationId != null) query.station_id = String(params.stationId);
    return api
      .get('/analytics/revenue', { params: query })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const s = (d.summary as Record<string, unknown>) ?? {};
        return {
          ...raw,
          data: {
            summary: {
              totalRevenue: (s.total_revenue as number) ?? 0,
              totalKwh: (s.total_kwh as number) ?? 0,
              totalOrders: (s.total_orders as number) ?? 0,
              avgPerOrder: (s.avg_per_order as number) ?? 0,
            },
            trend: (d.trend as unknown[]) ?? [],
          },
        };
      });
  },
};

// =====================
// 安全威胁 API (/security/threats)
// =====================
export const securityThreatApi = {
  /** GET /security/threats — 安全威胁列表 */
  getList(): Promise<ApiResponse<PaginatedData<SecurityThreat>>> {
    return api
      .get('/security/threats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          type: (it.type as string) ?? '',
          sourceIp: (it.source_ip as string) ?? '',
          target: (it.target as string) ?? '',
          severity: (it.severity as 'low' | 'medium' | 'high' | 'critical') ?? 'low',
          status: (it.status as 'blocked' | 'active' | 'resolved') ?? 'active',
          timestamp: (it.timestamp as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: 1,
            pageSize: items.length,
          },
        };
      });
  },
};

// =====================
// 通知统计 API (/notifications/stats)
// =====================
export const notificationStatsApi = {
  /** GET /notifications/stats — 通知统计 */
  getStats(): Promise<ApiResponse<NotificationStats>> {
    return api
      .get('/notifications/stats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            totalTemplates: (d.total_templates as number) ?? 0,
            totalMessages: (d.total_messages as number) ?? 0,
            sentToday: (d.sent_today as number) ?? 0,
            failedCount: (d.failed_count as number) ?? 0,
            channelDistribution: (d.channel_distribution as Record<string, number>) ?? {},
          },
        };
      });
  },
};

// =====================
// 未读通知计数 API (/notifications/unread-count)
// =====================
export const notificationUnreadApi = {
  /** GET /notifications/unread-count — 未读通知计数 */
  getUnreadCount(): Promise<ApiResponse<UnreadCount>> {
    return api
      .get('/notifications/unread-count')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            unreadCount: (d.unread_count as number) ?? 0,
          },
        };
      });
  },
};

// =====================
// 通知操作 API (POST /notifications/read-all, /notifications/{id}/read)
// =====================
export const notificationActionApi = {
  /** POST /notifications/read-all — 全部标记为已读 */
  readAll(): Promise<ApiResponse<ReadAllResult>> {
    return api
      .post('/notifications/read-all')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            markedCount: (d.marked_count as number) ?? 0,
          },
        };
      });
  },

  /** POST /notifications/{id}/read — 标记单条为已读 */
  readById(id: number | string): Promise<ApiResponse<null>> {
    return api.post(`/notifications/${id}/read`).then((res) => res.data as ApiResponse<null>);
  },
};

export const deviceHealthApi = {
  /** GET /health/devices — 设备健康度排名 */
  getRanking(): Promise<ApiResponse<DeviceHealthRanking>> {
    return api.get('/health/devices').then((res) => res.data as ApiResponse<DeviceHealthRanking>);
  },
};

// =====================
// 网关管理 API (/gateways)
// =====================
export interface GatewayCreate {
  sn: string;
  name: string;
  stationId?: number;
  model?: string;
  manufacturer?: string;
}

export const gatewayApi = {
  /** GET /gateways — 网关列表 */
  getList(): Promise<ApiResponse<PaginatedData<Gateway>>> {
    return api.get('/gateways').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): Gateway => ({
            id: item.id as number,
            sn: (item.sn as string) ?? '',
            name: (item.name as string) ?? '',
            model: (item.model as string) ?? null,
            manufacturer: (item.manufacturer as string) ?? null,
            stationId: (item.station_id as number) ?? null,
            status: (item.status as Gateway['status']) ?? 'offline',
            firmwareVersion: (item.firmware_version as string) ?? null,
            lastOnline: (item.last_online as string) ?? null,
            ipAddress: (item.ip_address as string) ?? null,
            macAddress: (item.mac_address as string) ?? null,
            location: (item.location as string) ?? null,
            healthScore: (item.health_score as number) ?? 0,
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? '',
            notes: (item.notes as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** GET /gateways/{id} — 网关详情 */
  getById(id: number): Promise<ApiResponse<Gateway>> {
    return api.get(`/gateways/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const item = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: item.id as number,
          sn: (item.sn as string) ?? '',
          name: (item.name as string) ?? '',
          model: (item.model as string) ?? null,
          manufacturer: (item.manufacturer as string) ?? null,
          stationId: (item.station_id as number) ?? null,
          status: (item.status as Gateway['status']) ?? 'offline',
          firmwareVersion: (item.firmware_version as string) ?? null,
          lastOnline: (item.last_online as string) ?? null,
          ipAddress: (item.ip_address as string) ?? null,
          macAddress: (item.mac_address as string) ?? null,
          location: (item.location as string) ?? null,
          healthScore: (item.health_score as number) ?? 0,
          createdAt: (item.created_at as string) ?? '',
          updatedAt: (item.updated_at as string) ?? '',
          notes: (item.notes as string) ?? null,
        },
      };
    });
  },

  /** GET /gateways/firmware — 固件包列表 */
  getFirmware(): Promise<ApiResponse<PaginatedData<GatewayFirmware>>> {
    return api.get('/gateways/firmware').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): GatewayFirmware => ({
            id: item.id as number,
            version: (item.version as string) ?? '',
            fileId: (item.file_id as string) ?? null,
            fileSize: (item.file_size as number) ?? null,
            releaseNotes: (item.release_notes as string) ?? null,
            status: (item.status as string) ?? null,
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** GET /gateways/status — 网关状态统计 */
  getStatus(): Promise<ApiResponse<GatewayStatus>> {
    return api.get('/gateways/status').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          onlineCount: (d.online_count as number) ?? 0,
          offlineCount: (d.offline_count as number) ?? 0,
          maintenanceCount: (d.maintenance_count as number) ?? 0,
          faultCount: (d.fault_count as number) ?? 0,
          total: (d.total as number) ?? 0,
        },
      };
    });
  },

  /** POST /gateways — 创建网关 */
  create(body: GatewayCreate): Promise<ApiResponse<Gateway>> {
    return api
      .post('/gateways', {
        sn: body.sn,
        name: body.name,
        ...(body.stationId !== undefined && { station_id: body.stationId }),
        ...(body.model !== undefined && { model: body.model }),
        ...(body.manufacturer !== undefined && { manufacturer: body.manufacturer }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            sn: (it.sn as string) ?? '',
            name: (it.name as string) ?? '',
            model: (it.model as string) ?? null,
            manufacturer: (it.manufacturer as string) ?? null,
            stationId: (it.station_id as number) ?? null,
            status: (it.status as Gateway['status']) ?? 'offline',
            firmwareVersion: (it.firmware_version as string) ?? null,
            lastOnline: (it.last_online as string) ?? null,
            ipAddress: (it.ip_address as string) ?? null,
            macAddress: (it.mac_address as string) ?? null,
            location: (it.location as string) ?? null,
            healthScore: (it.health_score as number) ?? 0,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
            notes: (it.notes as string) ?? null,
          },
        };
      });
  },

  /** DELETE /gateways/{id} — 删除网关 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/gateways/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};

// =====================
// 租户管理 API (/tenants)
// =====================
export interface TenantCreate {
  name: string;
  code: string;
}

export const tenantListApi = {
  /** GET /tenants — 租户列表 */
  getList(): Promise<ApiResponse<PaginatedData<Tenant>>> {
    return api.get('/tenants').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): Tenant => ({
            id: item.id as number,
            name: (item.name as string) ?? '',
            code: (item.code as string) ?? '',
            status: (item.status as string) ?? 'active',
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? '',
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** POST /tenants — 创建租户 */
  create(body: TenantCreate): Promise<ApiResponse<Tenant>> {
    return api
      .post('/tenants', {
        name: body.name,
        code: body.code,
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string) ?? '',
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /tenants/{id} — 删除租户 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/tenants/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};

// =====================
// VPP 虚拟电厂 API (/vpp/resources, POST /vpp/dispatch)
// =====================
export const vppApi = {
  /** GET /vpp/resources — VPP资源清单(光伏/储能/EV/负荷) */
  getResources(): Promise<ApiResponse<VppResource[]>> {
    return api.get('/vpp/resources').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const items = (raw.data as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: items.map((item): VppResource => ({
          resourceId: (item.resource_id as string) ?? '',
          resourceType: (item.resource_type as VppResourceType) ?? 'pv',
          stationId: (item.station_id as string) ?? '',
          ratedPowerKw: (item.rated_power_kw as number) ?? 0,
          currentPowerKw: (item.current_power_kw as number) ?? 0,
          availablePowerKw: (item.available_power_kw as number) ?? 0,
          soc: item.soc !== undefined && item.soc !== null ? (item.soc as number) : null,
          efficiency: (item.efficiency as number) ?? 0,
          priority: (item.priority as number) ?? 0,
          costPerKwh: (item.cost_per_kwh as number) ?? 0,
        })),
      };
    });
  },

  /** POST /vpp/dispatch — 触发VPP调度(削峰/填谷/调频/需求响应) */
  dispatch(body?: Record<string, unknown>): Promise<ApiResponse<VppDispatchPlan>> {
    return api.post('/vpp/dispatch', body ?? {}).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const commands = (d.commands as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          planId: (d.plan_id as string) ?? '',
          mode: (d.mode as VppDispatchMode) ?? 'peak_shaving',
          trigger: (d.trigger as string) ?? '',
          stationsInvolved: (d.stations_involved as string[]) ?? [],
          totalDispatchKw: (d.total_dispatch_kw as number) ?? 0,
          estimatedRevenue: (d.estimated_revenue as number) ?? 0,
          estimatedCost: (d.estimated_cost as number) ?? 0,
          netProfit: (d.net_profit as number) ?? 0,
          commands: commands.map((c): VppDispatchCommand => ({
            resourceId: (c.resource_id as string) ?? '',
            stationId: (c.station_id as string) ?? '',
            resourceType: (c.resource_type as VppResourceType) ?? 'battery',
            targetPowerKw: (c.target_power_kw as number) ?? 0,
            durationMin: (c.duration_min as number) ?? 0,
            priority: (c.priority as number) ?? 0,
            estimatedRevenue: (c.estimated_revenue as number) ?? 0,
            estimatedCost: (c.estimated_cost as number) ?? 0,
            dispatchMode: (c.dispatch_mode as VppDispatchMode) ?? 'peak_shaving',
          })),
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** GET /vpp/dispatch/history — VPP调度历史记录 */
  getDispatchHistory(): Promise<ApiResponse<VppDispatchHistory[]>> {
    return api.get('/vpp/dispatch/history').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const items = (raw.data as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: items.map((item): VppDispatchHistory => ({
          planId: (item.plan_id as string) ?? '',
          mode: (item.mode as VppDispatchMode) ?? 'peak_shaving',
          trigger: (item.trigger as string) ?? '',
          stationsInvolved: (item.stations_involved as string[]) ?? [],
          totalDispatchKw: (item.total_dispatch_kw as number) ?? 0,
          estimatedRevenue: (item.estimated_revenue as number) ?? 0,
          estimatedCost: (item.estimated_cost as number) ?? 0,
          netProfit: (item.net_profit as number) ?? 0,
          commandsCount: (item.commands_count as number) ?? 0,
          createdAt: (item.created_at as string) ?? '',
          executed: (item.executed as boolean) ?? false,
        })),
      };
    });
  },
};

// =====================
// AI 对话 API (POST /chat)
// =====================
export const chatApi = {
  /** POST /chat — 发送消息给AI助手 */
  send(message: string, options?: {
    conversationId?: string;
    context?: Record<string, unknown>;
  }): Promise<ApiResponse<ChatResponse>> {
    const body: Record<string, unknown> = { message };
    if (options?.conversationId) body.conversation_id = options.conversationId;
    if (options?.context) body.context = options.context;
    return api.post('/chat', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const sources = (d.sources as Record<string, unknown>[]) ?? [];
      const actions = (d.actions as Record<string, unknown>[]) ?? [];
      const usage = d.usage as Record<string, unknown> | null;
      return {
        ...raw,
        data: {
          answer: (d.answer as string) ?? '',
          confidence: (d.confidence as number) ?? 0,
          sources: sources.map((s): ChatSource => ({
            title: (s.title as string) ?? '',
            url: (s.url as string) ?? '',
            type: (s.type as string) ?? '',
          })),
          actions: actions.map((a): ChatAction => ({
            type: (a.type as string) ?? '',
            label: (a.label as string) ?? '',
            target: (a.target as string) ?? '',
          })),
          needsHuman: (d.needs_human as boolean) ?? false,
          usage: usage ? {
            promptTokens: (usage.prompt_tokens as number) ?? 0,
            completionTokens: (usage.completion_tokens as number) ?? 0,
            totalTokens: (usage.total_tokens as number) ?? 0,
          } : null,
        },
      };
    });
  },
};

// =====================
// 通知发送 API (POST /notifications/send)
// =====================
export const notificationSendApi = {
  /** POST /notifications/send — 发送通知给指定用户 */
  send(params: {
    userId: number;
    title: string;
    content: string;
    channel?: string;
    type?: string;
  }): Promise<ApiResponse<NotificationSendResult>> {
    const body: Record<string, unknown> = {
      user_id: params.userId,
      title: params.title,
      content: params.content,
    };
    if (params.channel) body.channel = params.channel;
    if (params.type) body.type = params.type;
    return api.post('/notifications/send', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          success: (d.success as boolean) ?? false,
          messageId: (d.message_id as string) ?? null,
          channel: (d.channel as string) ?? null,
          sentAt: (d.sent_at as string) ?? null,
        },
      };
    });
  },
};

// =====================
// 车队 API (GET /fleet/drivers)
// =====================
export const fleetApi = {
  /** GET /fleet/drivers — 司机列表 */
  getDrivers(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<FleetDriver>>> {
    const query: Record<string, unknown> = {};
    if (params?.page) query.page = params.page;
    if (params?.pageSize) query.page_size = params.pageSize;
    return api.get('/fleet/drivers', { params: query }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): FleetDriver => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            phone: (item.phone as string) ?? null,
            licenseNumber: (item.license_number as string) ?? null,
            vehiclePlate: (item.vehicle_plate as string) ?? null,
            status: (item.status as string) ?? 'unknown',
            createdAt: (item.created_at as string) ?? null,
            updatedAt: (item.updated_at as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },
};

// =====================
// Runbook 模板 API (GET /runbooks/templates)
// =====================
export const runbookTemplateApi = {
  /** GET /runbooks/templates — Runbook 模板列表 */
  getList(): Promise<ApiResponse<PaginatedData<RunbookTemplateSummary>>> {
    return api
      .get('/runbooks/templates')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          category: (it.category as string) ?? '',
          alarmType: (it.alarm_type as string) ?? '',
          description: (it.description as string) ?? '',
          stepCount: (it.step_count as number) ?? 0,
          autoSteps: (it.auto_steps as number) ?? 0,
          manualSteps: (it.manual_steps as number) ?? 0,
          status: (it.status as string) ?? 'active',
          version: (it.version as number) ?? 1,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? items.length,
            page: (d.page as number) ?? 1,
            pageSize: (d.page_size as number) ?? items.length,
          },
        };
      });
  },

  /** GET /runbooks/templates/{id} — Runbook 模板详情 (含步骤) */
  getById(id: number): Promise<ApiResponse<RunbookTemplateDetail>> {
    return api
      .get(`/runbooks/templates/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        const rawSteps = (it.steps as Record<string, unknown>[]) ?? [];
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            category: (it.category as string) ?? '',
            alarmType: (it.alarm_type as string) ?? '',
            description: (it.description as string) ?? '',
            stepCount: (it.step_count as number) ?? 0,
            autoSteps: (it.auto_steps as number) ?? 0,
            manualSteps: (it.manual_steps as number) ?? 0,
            status: (it.status as string) ?? 'active',
            version: (it.version as number) ?? 1,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
            steps: rawSteps.map((s) => ({
              stepId: (s.step_id as number) ?? 0,
              actionType: (s.action_type as string) ?? '',
              description: (s.description as string) ?? '',
              command: (s.command as string) ?? '',
              params: (s.params as Record<string, unknown>) ?? {},
              riskLevel: (s.risk_level as string) ?? 'low',
              timeoutSec: (s.timeout_sec as number) ?? 0,
              rollbackCommand: (s.rollback_command as string) ?? '',
              preCheck: (s.pre_check as string) ?? '',
              postCheck: (s.post_check as string) ?? '',
              autoExecute: (s.auto_execute as boolean) ?? false,
              status: (s.status as string) ?? 'pending',
              result: (s.result as string) ?? '',
              durationMs: (s.duration_ms as number) ?? 0,
              errorMessage: (s.error_message as string) ?? '',
            })),
          },
        };
      });
  },
};

// =====================
// 系统健康检查 API (GET /readyz + GET /livez + GET /health)
// =====================
export const healthApi = {
  /** GET /readyz — 详细就绪检查 (数据库/Redis/MQTT/文件系统) */
  getReadyz(): Promise<ApiResponse<SystemHealth>> {
    return api.get('/readyz').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const checks = (d.checks ?? {}) as Record<string, unknown>;
      const db = (checks.database ?? {}) as Record<string, unknown>;
      const redis = (checks.redis ?? {}) as Record<string, unknown>;
      const mqtt = (checks.mqtt_broker ?? {}) as Record<string, unknown>;
      const fs = (checks.filesystem ?? {}) as Record<string, unknown>;
      const fsPaths = (fs.paths ?? {}) as Record<string, Record<string, unknown>>;
      const paths: Record<string, { totalGb: number; freeGb: number; freePct: number }> = {};
      for (const [k, v] of Object.entries(fsPaths)) {
        paths[k] = {
          totalGb: (v.total_gb as number) ?? 0,
          freeGb: (v.free_gb as number) ?? 0,
          freePct: (v.free_pct as number) ?? 0,
        };
      }
      return {
        ...raw,
        data: {
          status: (d.status as HealthStatus) ?? 'error',
          checks: {
            database: {
              status: (db.status as HealthStatus) ?? 'error',
              poolSize: (db.pool_size as number) ?? 0,
              activeConnections: (db.active_connections as number) ?? 0,
              idleConnections: (db.idle_connections as number) ?? 0,
              waitingConnections: (db.waiting_connections as number) ?? 0,
              dbType: (db.db_type as string) ?? 'unknown',
            },
            redis: {
              status: (redis.status as HealthStatus) ?? 'error',
              version: (redis.version as string) ?? 'unknown',
              usedMemoryHuman: (redis.used_memory_human as string) ?? '0',
              connectedClients: (redis.connected_clients as number) ?? 0,
            },
            mqttBroker: {
              status: (mqtt.status as HealthStatus) ?? 'error',
              host: (mqtt.host as string) ?? 'unknown',
              port: (mqtt.port as number) ?? 0,
              error: (mqtt.error as string) ?? null,
            },
            filesystem: { paths },
          },
          uptimeSeconds: (d.uptime_seconds as number) ?? 0,
          unhealthyChecks: (d.unhealthy_checks as string[]) ?? [],
        },
      };
    });
  },

  /** GET /livez — 存活探针 */
  getLivez(): Promise<LivenessProbe> {
    return api.get('/livez').then((res) => {
      const d = (res.data ?? {}) as Record<string, unknown>;
      return {
        status: (d.status as string) ?? 'unknown',
        uptimeSeconds: (d.uptime_seconds as number) ?? 0,
      };
    });
  },

  /** GET /ping — 连通性检查 (返回pong) */
  getPing(): Promise<ApiResponse<{ message: string }>> {
    return api.get('/ping').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          message: (d.message as string) ?? '',
        },
      };
    });
  },

  /** GET /health — 简要健康信息 */
  getHealth(): Promise<ApiResponse<HealthInfo>> {
    return api.get('/health').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          status: (d.status as string) as HealthStatus ?? 'error',
          version: (d.version as string) ?? 'unknown',
          service: (d.service as string) ?? 'unknown',
        },
      };
    });
  },
};

// =====================
// 缓存统计 API (GET /cache/stats)
// =====================
export const cacheApi = {
  /** GET /cache/stats — Redis 缓存统计 (命中率/键数/内存/后端) */
  getStats(): Promise<ApiResponse<CacheStats>> {
    return api.get('/cache/stats').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          hitRate: (d.hit_rate as number) ?? 0,
          totalKeys: (d.total_keys as number) ?? 0,
          usedMemoryMb: (d.used_memory_mb as number) ?? 0,
          backend: (d.backend as string) ?? 'unknown',
        },
      };
    });
  },
};

// =====================
// 站点 API (GET /stations, GET /stations/{id})
// =====================
function mapStation(raw: Record<string, unknown>): Station {
  const brandingRaw = (raw.branding ?? null) as Record<string, unknown> | null;
  let branding: StationBranding | null = null;
  if (brandingRaw) {
    branding = {
      operatorName: (brandingRaw.operator_name as string) ?? '',
      logoUrl: (brandingRaw.logo_url as string) ?? '',
      servicePhone: (brandingRaw.service_phone as string) ?? '',
      themeColor: (brandingRaw.theme_color as string) ?? '#00A86B',
      source: (brandingRaw.source as string) ?? 'default',
    };
  }
  return {
    id: (raw.id as number) ?? 0,
    name: (raw.name as string) ?? '',
    code: (raw.code as string) ?? '',
    province: (raw.province as string) ?? '',
    city: (raw.city as string) ?? '',
    district: (raw.district as string) ?? '',
    address: (raw.address as string) ?? '',
    lat: (raw.lat as number) ?? 0,
    lon: (raw.lon as number) ?? 0,
    status: (raw.status as Station['status']) ?? 'normal',
    stationType: (raw.station_type as string | null) ?? null,
    operatorId: (raw.operator_id as number | null) ?? null,
    operatorName: (raw.operator_name as string | null) ?? null,
    teamId: (raw.team_id as number | null) ?? null,
    totalPower: (raw.total_power as number) ?? 0,
    totalDevices: (raw.total_devices as number) ?? 0,
    gunCount: (raw.gun_count as number) ?? 0,
    venueType: (raw.venue_type as string | null) ?? null,
    totalCost: (raw.total_cost as number | null) ?? null,
    parkingSpots: (raw.parking_spots as number | null) ?? null,
    healthScore: (raw.health_score as number) ?? 0,
    branding,
    createdAt: (raw.created_at as string) ?? '',
    updatedAt: (raw.updated_at as string | null) ?? null,
  };
}

export const stationApi = {
  /** GET /stations — 站点列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
    status?: string;
    keyword?: string;
  }): Promise<ApiResponse<PaginatedData<Station>>> {
    const query: Record<string, string> = {};
    if (params?.page != null) query.page = String(params.page);
    if (params?.pageSize != null) query.page_size = String(params.pageSize);
    if (params?.status != null) query.status = params.status;
    if (params?.keyword != null) query.keyword = params.keyword;
    return api.get('/stations', { params: query }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items ?? []) as Record<string, unknown>[]).map(mapStation);
      return {
        ...raw,
        data: {
          items,
          total: (d.total as number) ?? items.length,
          page: (d.page as number) ?? (params?.page ?? 1),
          pageSize: (d.page_size as number) ?? (params?.pageSize ?? 20),
        },
      };
    });
  },

  /** GET /stations/{id} — 站点详情 */
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: mapStation((raw.data ?? {}) as Record<string, unknown>) };
    });
  },
};

// =====================
// 团队 API (teams — /teams)
// =====================
export const teamApi = {
  /** GET /teams — 团队列表 */
  getList(params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<Team>>> {
    const query = params ? `?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` : '';
    return api
      .get(`/teams${query}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          code: (it.code as string | null) ?? null,
          leaderId: (it.leader_id as number | null) ?? null,
          leaderName: (it.leader_name as string | null) ?? null,
          description: (it.description as string | null) ?? null,
          memberCount: (it.member_count as number) ?? 0,
          stationCount: (it.station_count as number) ?? 0,
          status: (it.status as string) ?? 'active',
          createdAt: (it.created_at as string | null) ?? null,
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? items.length,
            page: (d.page as number) ?? (params?.page ?? 1),
            pageSize: (d.page_size as number) ?? (params?.page_size ?? 20),
          },
        };
      });
  },

  /** GET /teams/{id} — 团队详情 */
  getDetail(id: number): Promise<ApiResponse<Team>> {
    return api
      .get(`/teams/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** PUT /teams/{id} — 更新团队 */
  update(id: number, body: TeamUpdate): Promise<ApiResponse<Team>> {
    // camel → snake for request body
    const payload: Record<string, unknown> = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.description !== undefined) payload.description = body.description;
    if (body.leaderId !== undefined) payload.leader_id = body.leaderId;
    if (body.status !== undefined) payload.status = body.status;
    return api
      .put(`/teams/${id}`, payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** POST /teams — 创建团队 */
  create(body: TeamCreate): Promise<ApiResponse<Team>> {
    const payload: Record<string, unknown> = { name: body.name };
    if (body.code !== undefined) payload.code = body.code;
    if (body.description !== undefined) payload.description = body.description;

    return api
      .post('/teams', payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** DELETE /teams/{id} — 删除团队 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/teams/${id}`).then((res) => {
      return res.data as ApiResponse<null>;
    });
  },
};
