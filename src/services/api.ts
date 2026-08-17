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
  AlarmLevel,
  AlarmStatus,
  WorkOrder,
  WorkOrderPriority,
  WorkOrderStatus,
  PaginatedData,
  DashboardStats,
  RevenueRecord,
  RevenueQuery,
  DeviceTelemetry,
  DeviceHealth,
  CreateWorkOrderData,
  ChargerStatus,
  ChargerMonitorSummary,
  ChargerTrend,
  AppNotification,
  EnergySummary,
  ReportSummary,
  DeviceConfig,
  DeviceReport,
  AlarmReport,
} from '../types';

const TOKEN_KEY = 'auth_token';
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? 'http://localhost:8000/api/v1' : 'http://8.134.106.166/api/v1');

// eslint-disable-next-line import/no-named-as-default-member -- axios 默认导出承载 .create; 此版本无 'axios' 具名导出(F1203实证), AxiosError/InternalAxiosRequestConfig 需同源默认导入
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
// 真云端契约归一化 (闭环战役B2: snake_case → camelCase)
// =====================

// 告警级别: 后端含 fatal, 归一到 UI 三档
const ALARM_LEVEL_MAP: Record<string, AlarmLevel> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
  fatal: 'critical',
};

// 告警状态: 后端 active/acknowledged/resolved/ignored → UI 三态
const ALARM_STATUS_MAP: Record<string, AlarmStatus> = {
  active: 'unhandled',
  acknowledged: 'processing',
  resolved: 'resolved',
  ignored: 'resolved',
};

// UI 状态 → 后端查询参数
const ALARM_STATUS_REVERSE: Record<string, string> = {
  unhandled: 'active',
  processing: 'acknowledged',
  resolved: 'resolved',
};

const ALARM_TYPE_LABEL: Record<string, string> = {
  high_temperature: '温度过高',
  device_fault: '设备故障',
  power_anomaly: '功率异常',
  communication_loss: '通讯中断',
  temperature_warning: '温度预警',
  health_warning: '健康度告警',
  offline: '设备离线',
};

// 工单级别: 后端 P0/P1/P2/warning/info → UI 优先级
const WO_LEVEL_TO_PRIORITY: Record<string, WorkOrderPriority> = {
  P0: 'urgent',
  P1: 'high',
  P2: 'normal',
  warning: 'low',
  info: 'low',
  critical: 'high',
  fatal: 'urgent',
};

const WO_PRIORITY_TO_LEVEL: Record<WorkOrderPriority, string> = {
  urgent: 'P0',
  high: 'P1',
  normal: 'P2',
  low: 'warning',
};

// 工单状态: 后端 pending/accepted/processing/completed/pending_verify/verified → UI 三态
const WO_STATUS_MAP: Record<string, WorkOrderStatus> = {
  pending: 'pending',
  accepted: 'in_progress',
  processing: 'in_progress',
  completed: 'completed',
  pending_verify: 'completed',
  verified: 'completed',
};

const WO_STATUS_REVERSE: Record<string, string> = {
  pending: 'pending',
  in_progress: 'processing',
  completed: 'completed',
};

type Raw = Record<string, unknown>;

// ── type-safe accessors for Raw ──
const num = (v: unknown, d = 0): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) || d : d;
const str = (v: unknown, d = ''): string =>
  v == null ? d : typeof v === 'string' ? v : String(v);
const numOrUndef = (v: unknown): number | undefined =>
  v == null ? undefined : typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) || undefined : undefined;
const strOrUndef = (v: unknown): string | undefined =>
  v == null ? undefined : typeof v === 'string' ? v : String(v);

export function mapAlarm(raw: Raw): Alarm {
  const alarmType = str(raw.alarm_type, 'other');
  return {
    id: num(raw.id),
    stationId: num(raw.station_id),
    stationName: str(raw.station_name),
    deviceId: numOrUndef(raw.device_id),
    deviceName: strOrUndef(raw.device_name),
    type: (ALARM_TYPE_LABEL[alarmType] ? alarmType : 'other') as Alarm['type'],
    level: ALARM_LEVEL_MAP[str(raw.level)] ?? 'info',
    title: ALARM_TYPE_LABEL[alarmType] ?? alarmType,
    description: str(raw.content),
    status: ALARM_STATUS_MAP[str(raw.status)] ?? 'unhandled',
    handledAt: strOrUndef(raw.handled_at),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.handled_at ?? raw.created_at),
  };
}

export function mapWorkOrder(raw: Raw): WorkOrder {
  const level = str(raw.level, 'warning');
  const status = str(raw.status, 'pending');
  return {
    id: str(raw.id),
    stationId: num(raw.station_id),
    stationName: str(raw.station_name, `站点${str(raw.station_id)}`),
    title: str(raw.fault_desc ?? raw.title, '工单'),
    description: str(raw.fault_desc ?? raw.description),
    type: str(raw.type, 'other') as WorkOrder['type'],
    priority: WO_LEVEL_TO_PRIORITY[level] ?? 'normal',
    status: WO_STATUS_MAP[status] ?? 'pending',
    assigneeId: numOrUndef(raw.assignee_id),
    assigneeName: strOrUndef(raw.assignee_name),
    creatorId: num(raw.creator_id),
    creatorName: str(raw.creator_name),
    alarmId: numOrUndef(raw.alarm_id),
    solution: strOrUndef(raw.solution),
    completedAt: strOrUndef(raw.finish_time),
    createdAt: str(raw.create_time ?? raw.created_at),
    updatedAt: str(raw.finish_time ?? raw.create_time),
  };
}

export function mapStation(raw: Raw): Station {
  const rawStatus = str(raw.status);
  const status = rawStatus === 'normal' || rawStatus === 'online' ? 'online'
    : rawStatus === 'maintenance' ? 'maintenance' : 'offline';
  return {
    id: num(raw.id),
    name: str(raw.name),
    code: str(raw.code),
    address: str(raw.address),
    status,
    latitude: num(raw.lat ?? raw.latitude),
    longitude: num(raw.lon ?? raw.longitude),
    deviceCount: num(raw.total_devices ?? raw.device_count),
    onlineDeviceCount: num(raw.online_devices ?? raw.total_devices),
    alarmCount: num(raw.alarm_count),
    healthScore: numOrUndef(raw.health_score),
    totalPower: numOrUndef(raw.total_power),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.updated_at ?? raw.created_at),
  };
}

export function mapPagination<T>(raw: Raw, mapper: (r: Raw) => T): PaginatedData<T> {
  return {
    items: Array.isArray(raw?.items) ? (raw.items as Raw[]).map(mapper) : [],
    total: num(raw?.total),
    page: num(raw?.page, 1),
    pageSize: num(raw?.page_size ?? raw?.pageSize, 20),
  };
}

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
// 认证 API (真云端: OAuth2 form-urlencoded, token 键为 token)
// =====================
export const authApi = {
  login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const form = new URLSearchParams();
    form.append('username', data.username);
    form.append('password', data.password);
    return api
      .post('/auth/login', form.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .then((res) => res.data);
  },
  logout(): Promise<ApiResponse<null>> {
    return api.post('/auth/logout').then((res) => res.data);
  },
  getProfile(): Promise<ApiResponse<User>> {
    return api.get('/auth/me').then((res) => res.data);
  },
};

// =====================
// 站点 API
// =====================
export const stationApi = {
  getList(params?: { page?: number; pageSize?: number; search?: string }): Promise<ApiResponse<PaginatedData<Station>>> {
    const query = {
      page: params?.page,
      page_size: params?.pageSize,
      search: params?.search,
    };
    return api.get('/stations', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Station>(res.data?.data, mapStation),
    }));
  },
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => ({
      ...res.data,
      data: mapStation(res.data?.data ?? {}),
    }));
  },
  getDevices(stationId: number): Promise<ApiResponse<Device[]>> {
    return api.get(`/stations/${stationId}/devices`).then((res) => res.data);
  },
  getAlarms(stationId: number, params?: { page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    const query = { page: params?.page, page_size: params?.pageSize };
    return api.get(`/stations/${stationId}/alarms`, { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Alarm>(res.data?.data, mapAlarm),
    }));
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
  getHealth(deviceId: number): Promise<ApiResponse<DeviceHealth>> {
    return api.get(`/devices/${deviceId}/health`).then((res) => {
      const d = res.data.data;
      return {
        ...res.data,
        data: {
          deviceId: d.device_id ?? d.deviceId ?? deviceId,
          healthScore: d.health_score ?? d.healthScore ?? 0,
          healthStatus: d.health_status ?? d.healthStatus ?? 'good',
          dimensionScores: d.dimension_scores ?? d.dimensionScores ?? {},
          checkedAt: d.checked_at ?? d.checkedAt ?? new Date().toISOString(),
        },
      };
    });
  },
  controlDevice(deviceId: number, command: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return api.post(`/devices/${deviceId}/control`, { command }).then((res) => res.data);
  },
  /** GET /devices/{id}/config — 充电桩配置 (仅充电桩设备) */
  getConfig(deviceId: number): Promise<ApiResponse<DeviceConfig>> {
    return api.get(`/devices/${deviceId}/config`).then((res) => {
      const d = res.data.data;
      return {
        ...res.data,
        data: {
          deviceId: d.device_id ?? d.deviceId ?? deviceId,
          voltageLimit: d.voltage_limit ?? d.voltageLimit ?? 0,
          currentLimit: d.current_limit ?? d.currentLimit ?? 0,
          maxPower: d.max_power ?? d.maxPower ?? 0,
          chargeMode: d.charge_mode ?? d.chargeMode ?? 'standard',
          overloadProtection: d.overload_protection ?? d.overloadProtection ?? false,
          timePeriods: (d.time_periods ?? d.timePeriods ?? []).map((p: Record<string, unknown>) => ({
            start: (p.start as string) ?? '',
            end: (p.end as string) ?? '',
            maxPower: (p.max_power as number) ?? (p.maxPower as number) ?? 0,
          })),
        },
      };
    });
  },
};

// =====================
// 告警 API (真云端: /alarms, 状态 active/acknowledged/resolved)
// =====================
export const alarmApi = {
  getList(params?: {
    stationId?: number;
    level?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Alarm>>> {
    const query = {
      station_id: params?.stationId,
      level: params?.level,
      status: params?.status ? (ALARM_STATUS_REVERSE[params.status] ?? params.status) : undefined,
      page: params?.page,
      page_size: params?.pageSize,
    };
    return api.get('/alarms', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<Alarm>(res.data?.data, mapAlarm),
    }));
  },
  getDetail(id: number): Promise<ApiResponse<Alarm>> {
    return api.get(`/alarms/${id}`).then((res) => ({
      ...res.data,
      data: mapAlarm(res.data?.data ?? {}),
    }));
  },
  // 真云端无 /handle 端点, 对齐 PUT /{id}/ack (确认告警)
  handleAlarm(id: number): Promise<ApiResponse<Alarm>> {
    return api.put(`/alarms/${id}/ack`).then((res) => ({
      ...res.data,
      data: res.data?.data ? mapAlarm(res.data.data) : undefined,
    }));
  },
};

// =====================
// 工单 API (真云端: /work-orders, id 为 WO- 字符串, snake_case)
// =====================
export const workOrderApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<WorkOrder>>> {
    const query = {
      station_id: params?.stationId,
      status: params?.status ? (WO_STATUS_REVERSE[params.status] ?? params.status) : undefined,
      page: params?.page,
      page_size: params?.pageSize,
    };
    return api.get('/work-orders', { params: query }).then((res) => ({
      ...res.data,
      data: mapPagination<WorkOrder>(res.data?.data, mapWorkOrder),
    }));
  },
  getDetail(id: string): Promise<ApiResponse<WorkOrder>> {
    return api.get(`/work-orders/${id}`).then((res) => ({
      ...res.data,
      data: mapWorkOrder(res.data?.data ?? {}),
    }));
  },
  createWorkOrder(data: CreateWorkOrderData): Promise<ApiResponse<WorkOrder>> {
    const body = {
      fault_desc: data.title,
      type: data.type,
      level: WO_PRIORITY_TO_LEVEL[data.priority] ?? 'warning',
      station_id: data.stationId,
      device_id: data.deviceId ?? null,
    };
    return api.post('/work-orders', body).then((res) => ({
      ...res.data,
      data: res.data?.data ? mapWorkOrder(res.data.data) : undefined,
    }));
  },
  // 真云端 complete 的 solution 是 query 参数
  completeWorkOrder(id: string, solution?: string): Promise<ApiResponse<WorkOrder>> {
    return api
      .post(`/work-orders/${id}/complete`, null, { params: solution ? { solution } : undefined })
      .then((res) => ({
        ...res.data,
        data: res.data?.data ? mapWorkOrder(res.data.data) : undefined,
      }));
  },
  getStats(): Promise<ApiResponse<{
    total: number;
    status_distribution: Record<string, number>;
    level_distribution: Record<string, number>;
    type_distribution: Record<string, number>;
  }>> {
    return api.get('/work-orders/stats').then((res) => res.data);
  },
};

// =====================
// Dashboard API (真云端无专用端点, 聚合 work-orders/stats + alarms + stations)
// =====================
export const dashboardApi = {
  async getStats(): Promise<ApiResponse<DashboardStats>> {
    const [woStats, activeAlarms, allAlarms, stations] = await Promise.all([
      workOrderApi.getStats(),
      api.get('/alarms', { params: { status: 'active', page: 1, page_size: 1 } }),
      api.get('/alarms', { params: { page: 1, page_size: 1 } }),
      stationApi.getList({ page: 1, pageSize: 100 }),
    ]);
    const list = stations.data?.items ?? [];
    const online = list.filter((s) => s.status === 'online').length;
    return {
      code: 200,
      message: 'success',
      data: {
        totalStations: stations.data?.total ?? list.length,
        onlineStations: online,
        offlineStations: Math.max(0, (stations.data?.total ?? list.length) - online),
        totalAlarms: allAlarms.data?.data?.total ?? 0,
        unhandledAlarms: activeAlarms.data?.data?.total ?? 0,
        pendingWorkOrders: woStats.data?.status_distribution?.pending ?? 0,
        totalWorkOrders: woStats.data?.total ?? 0,
      },
    };
  },
  getRecentAlarms(limit = 5): Promise<ApiResponse<Alarm[]>> {
    return api.get('/alarms', { params: { page: 1, page_size: limit } }).then((res) => ({
      ...res.data,
      data: (res.data?.data?.items ?? []).map(mapAlarm),
    }));
  },
};

// =====================
// 营收 API (闭环战役A3 经营域: /business/*, 云端待部署)
// =====================
export const revenueApi = {
  // 汇总: 今日/本周/本月/累计 = 全量 + daily(30天) 客户端聚合
  async getSummary(): Promise<ApiResponse<{ today: number; week: number; month: number; total: number }>> {
    const [totalRes, dailyRes] = await Promise.all([
      api.get('/business/revenue/summary'),
      api.get('/business/revenue/daily', { params: { days: 30 } }),
    ]);
    const total = totalRes.data?.data?.net_revenue ?? 0;
    const daily: { date: string; net_revenue: number }[] = dailyRes.data?.data ?? [];
    const month = daily.reduce((s, d) => s + (d.net_revenue || 0), 0);
    const week = daily.slice(-7).reduce((s, d) => s + (d.net_revenue || 0), 0);
    const today = daily.length > 0 ? daily[daily.length - 1]!.net_revenue || 0 : 0;
    return {
      code: 200,
      message: 'success',
      data: {
        today: Math.round(today * 100) / 100,
        week: Math.round(week * 100) / 100,
        month: Math.round(month * 100) / 100,
        total: Math.round(total * 100) / 100,
      },
    };
  },
  // 明细: day→近7天, week→近7天, month→近30天
  getRecords(query: RevenueQuery): Promise<ApiResponse<RevenueRecord[]>> {
    const days = query.type === 'month' ? 30 : 7;
    return api.get('/business/revenue/daily', { params: { days } }).then((res) => ({
      ...res.data,
      data: (res.data?.data ?? []).map((d: Raw) => ({
        date: str(d.date),
        amount: num(d.net_revenue),
        orderCount: num(d.order_count),
      })),
    }));
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
  // 充电桩实时趋势（功率/电压/电流/SOC 历史曲线）
  getTrend(deviceId: number, params?: { points?: number }): Promise<ApiResponse<ChargerTrend>> {
    return api.get(`/devices/${deviceId}/charger-trend`, { params }).then((res) => res.data);
  },
};

// =====================
// 能源概览 API (GET /energy/summary)
// =====================
export const energyApi = {
  getSummary(): Promise<ApiResponse<EnergySummary>> {
    return api.get('/energy/summary').then((res) => {
      const d = res.data?.data as Raw | undefined;
      if (!d) {return res.data;}
      return {
        ...res.data,
        data: {
          period: str(d.period),
          days: num(d.days),
          pvGeneration: num(d.pv_generation),
          chargingAmount: num(d.charging_amount),
          dischargeAmount: num(d.discharge_amount),
          pvRevenue: num(d.pv_revenue),
          chargingRevenue: num(d.charging_revenue),
          dischargeRevenue: num(d.discharge_revenue),
          totalRevenue: num(d.total_revenue),
          yoy: {
            pvGenerationYoY: num((d.yoy as Raw | undefined)?.pv_generation_yoy),
            chargingAmountYoY: num((d.yoy as Raw | undefined)?.charging_amount_yoy),
            dischargeAmountYoY: num((d.yoy as Raw | undefined)?.discharge_amount_yoy),
            totalRevenueYoY: num((d.yoy as Raw | undefined)?.total_revenue_yoy),
          },
          priceInfo: {
            feedInTariff: num((d.price_info as Raw | undefined)?.feed_in_tariff),
            chargingPrice: num((d.price_info as Raw | undefined)?.charging_price),
            dischargePrice: num((d.price_info as Raw | undefined)?.discharge_price),
          },
        },
      };
    });
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

// =====================
// 运维报表 API (GET /reports/summary)
// =====================
export const reportApi = {
  /** GET /reports/summary — 30天运维报表摘要 */
  getSummary(): Promise<ApiResponse<ReportSummary>> {
    return api.get('/reports/summary').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const sh = (d.station_health as Record<string, unknown>) ?? {};
      const dist = (sh.distribution as Record<string, number>) ?? {};
      return {
        ...raw,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          overview: {
            totalDevices: (ov.total_devices as number) ?? 0,
            onlineDevices: (ov.online_devices as number) ?? 0,
            offlineDevices: (ov.offline_devices as number) ?? 0,
            faultDevices: (ov.fault_devices as number) ?? 0,
            maintenanceDevices: (ov.maintenance_devices as number) ?? 0,
            onlineRate: (ov.online_rate as number) ?? 0,
            totalStations: (ov.total_stations as number) ?? 0,
            totalWorkorders: (ov.total_workorders as number) ?? 0,
            completedWorkorders: (ov.completed_workorders as number) ?? 0,
            completionRate: (ov.completion_rate as number) ?? 0,
            totalAlarms: (ov.total_alarms as number) ?? 0,
            activeAlarms: (ov.active_alarms as number) ?? 0,
          },
          stationHealth: {
            normal: dist.normal ?? 0,
            warning: dist.warning ?? 0,
            critical: dist.critical ?? 0,
            offline: dist.offline ?? 0,
            healthyRate: (sh.healthy_rate as number) ?? 0,
          },
        },
      };
    });
  },
  /** GET /reports/devices — 30天设备报告 */
  getDevices(): Promise<ApiResponse<DeviceReport>> {
    return api.get('/reports/devices').then((res) => {
      const d = (res.data.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const typeDist = (d.type_distribution as Record<string, number>) ?? {};
      const statusDist = (d.status_distribution as Record<string, number>) ?? {};
      const stationDist = (d.station_distribution as Record<string, number>) ?? {};
      return {
        ...res.data,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalDevices: (ov.total_devices as number) ?? 0,
          onlineDevices: (ov.online_devices as number) ?? 0,
          offlineDevices: (ov.offline_devices as number) ?? 0,
          faultDevices: (ov.fault_devices as number) ?? 0,
          maintenanceDevices: (ov.maintenance_devices as number) ?? 0,
          typeDistribution: typeDist,
          statusDistribution: statusDist,
          stationDistribution: stationDist,
        },
      };
    });
  },
  /** GET /reports/alarms — 30天告警报告 */
  getAlarms(): Promise<ApiResponse<AlarmReport>> {
    return api.get('/reports/alarms').then((res) => {
      const d = (res.data.data ?? {}) as Record<string, unknown>;
      const ov = (d.overview as Record<string, unknown>) ?? {};
      const levelDist = (d.level_distribution as Record<string, number>) ?? {};
      const typeDist = (d.type_distribution as Record<string, number>) ?? {};
      const trend = (d.trend as Record<string, unknown>[]) ?? [];
      const topFaults = (d.top_fault_devices as Record<string, unknown>[]) ?? [];
      return {
        ...res.data,
        data: {
          periodDays: (d.period_days as number) ?? 30,
          totalAlarms: (ov.total_alarms as number) ?? 0,
          activeAlarms: (ov.active_alarms as number) ?? 0,
          resolvedAlarms: (ov.resolved_alarms as number) ?? 0,
          levelDistribution: levelDist,
          typeDistribution: typeDist,
          trend: trend.map((t) => ({ date: (t.date as string) ?? '', count: (t.count as number) ?? 0 })),
          topFaultDevices: topFaults.map((f) => ({
            deviceId: (f.device_id as number) ?? (f.deviceId as number) ?? 0,
            deviceName: (f.device_name as string) ?? (f.deviceName as string) ?? '',
            alarmCount: (f.alarm_count as number) ?? (f.alarmCount as number) ?? 0,
          })),
        },
      };
    });
  },
};
