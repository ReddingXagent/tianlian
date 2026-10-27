import axios, { type AxiosResponse } from 'axios';
import { message } from 'antd';
import { getToken, clearAuth } from '../utils/authStorage';
import { getCurrentTeamId } from '../utils/team';
import type {
  Station, StationCreateRequest, StationUpdateRequest,
  BusinessStation, BusinessStationListParams,
  Device,
  Alarm, AlarmCreateRequest, AlarmUpdateRequest,
  WorkOrder, WorkOrderCreateRequest,
  User, UserCreateRequest, UserUpdateRequest,
  Gateway, GatewayCreateRequest, GatewayUpdateRequest,
  PaginatedData,
} from '../types';

export { formatApiError, withRetry } from '../utils/errorHandler';
export { fetchAllPages, FETCH_ALL_PAGE_SIZE } from './fetchAll';

const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// 请求拦截器 - 添加 Authorization + X-Team-Id (团队隔离) header
api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // 团队隔离: 后端按 X-Team-Id 过滤数据, team_id=0 为平台默认
    config.headers['X-Team-Id'] = String(getCurrentTeamId());
    return config;
  },
  (error) => Promise.reject(error)
);

let isRedirecting = false;

// 业务错误码弹窗去重: 同 message 文本 1 秒内只弹一次, 防并发请求同错误刷屏
let lastBusinessErrorText = '';
let lastBusinessErrorTime = 0;
const BUSINESS_ERROR_DEDUP_MS = 1000;

// 响应拦截器 - 业务码校验(code≠200→失败) + 统一解包 {code,data,message} + 401处理
api.interceptors.response.use(
  (response) => {
    const body = response.data;
    // 仅对后端统一响应包装(含 code 字段)做业务码校验;
    // 二进制/blob/无 code 字段的响应一律放行(不解包、不校验)。
    if (body && typeof body === 'object' && 'code' in body) {
      // 成功码判定: 管理侧 code=200; C端 /business/ 入口走用户端云端契约 code=0 (契约 §6)。
      const reqUrl = response.config?.url || '';
      const isBusinessSuccess = reqUrl.includes('/business/') && body.code === 0;
      // HTTP 200 但 body.code 非成功 → 后端 error_response(code=400/404/500)。
      // 旧逻辑会把 data(常为 null)解包后当成功返回 → 删除/操作失败却提示成功。此处统一转失败。
      if (body.code !== 200 && !isBusinessSuccess) {
        const text = body.message || '操作失败';
        const now = Date.now();
        if (text !== lastBusinessErrorText || now - lastBusinessErrorTime >= BUSINESS_ERROR_DEDUP_MS) {
          lastBusinessErrorText = text;
          lastBusinessErrorTime = now;
          message.error(text);
        }
        return Promise.reject(
          Object.assign(new Error(text), { code: body.code, response: body })
        );
      }
      // code === 200: 保持原有解包逻辑(自动解套内层 data)
      if ('data' in body) {
        response.data = body.data;
      }
    }
    return response;
  },
  (error) => {
    // 403 团队越权 (卡 d0c431d0): 后端 cf614348 scope 矩阵拒绝跨团队/越权配置访问,
    // 前端统一兜底为去重提示并 reject (非鉴权失败, 不清凭证不跳登录)。
    if (error.response?.status === 403) {
      const text = '权限不足，无法访问该团队资源';
      const now = Date.now();
      if (text !== lastBusinessErrorText || now - lastBusinessErrorTime >= BUSINESS_ERROR_DEDUP_MS) {
        lastBusinessErrorText = text;
        lastBusinessErrorTime = now;
        message.error(text);
      }
    }
    if (error.response?.status === 401) {
      // 如果是登录请求的401，不要跳回登录页
      const url = error.config?.url || '';
      if (url.includes('/auth/login')) {
        return Promise.reject(error);
      }
      // 防抖：避免多个 401 并发触发多次重定向
      if (!isRedirecting) {
        isRedirecting = true;
        console.warn('[Auth] 收到 401，清除凭证并跳转登录页。URL:', url);
        clearAuth();
        localStorage.removeItem('entry_type');
        // 延迟跳转，避免其他并发请求的 401 重复处理
        setTimeout(() => {
          window.location.href = '/login';
        }, 100);
      }
    }
    return Promise.reject(error);
  }
);

export default api;

export const authAPI = {
  login: (username: string, password: string, userType?: string) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    if (userType) {
      formData.append('user_type', userType);
    }
    return api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  // 短信验证码
  smsSend: (phone: string, purpose: string = 'login') =>
    api.post('/auth/sms/send', { phone, purpose }),
  smsVerify: (phone: string, code: string, purpose: string = 'login') =>
    api.post('/auth/sms/verify', { phone, code, purpose }),
  // 验证码登录
  smsLogin: (phone: string, code: string, userType?: string) =>
    api.post('/auth/sms/login', { phone, code, user_type: userType }),
  // 两步登录第二步 (任务卡 78c7404b): temp_token + 短信码换正式 token
  verify2FA: (tempToken: string, code: string) =>
    api.post('/auth/login/verify-2fa', { temp_token: tempToken, code }),
  // 企业注册(任务卡 78c7404b): 上传执照 + 提交注册申请(匿名, 走 /auth/register/*)
  uploadLicense: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/auth/register/upload-license', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  registerEnterprise: (payload: Record<string, unknown>) =>
    api.post('/auth/register/enterprise', payload),
  // 密码重置
  passwordReset: (phone: string, code: string, newPassword: string) =>
    api.post('/auth/password-reset', { phone, code, new_password: newPassword }),
};

export const stationAPI = {
  // ── 管理端 CRUD: 保留 /stations (按 caller team 隔离 + 运维内部字段, 需 station 权限) ──
  // params 可选 team_id（卡 2285f54a：admin 按团队过滤，供 Tenants TeamDataView）
  list: (params?: Record<string, unknown>) => api.get('/stations', { params }),
  get: (id: number) => api.get(`/stations/${id}`),
  create: (data: StationCreateRequest) => api.post<Station>('/stations', data),
  update: (id: number, data: StationUpdateRequest) => api.put<Station>(`/stations/${id}`, data),
  delete: (id: number) => api.delete(`/stations/${id}`),
  assign: (id: number, teamId: number) => api.put(`/stations/${id}/assign`, { team_id: teamId }),
  // ── C端只读入口 (契约 §1): /business/stations, 信封 code=0, 不按 team 隔离, 跨运营商浏览 ──
  // 列表: lat+lon 同传进入 nearby 模式(按距离过滤排序 + 携带 distance_km); 返回 {items,total,page,page_size}
  businessList: (params?: BusinessStationListParams) =>
    api.get<PaginatedData<BusinessStation>>('/business/stations', { params }),
  businessGet: (id: number) => api.get<BusinessStation>(`/business/stations/${id}`),
};

export const deviceAPI = {
  list: (params?: Record<string, unknown>) => api.get<PaginatedData<Device>>('/devices', { params }),
  get: (id: number) => api.get<Device>(`/devices/${id}`),
  health: (id: number) => api.post(`/devices/${id}/health`),
  create: (data: Record<string, unknown>) => api.post<Device>('/devices', data),
  update: (id: number, data: Record<string, unknown>) => api.put<Device>(`/devices/${id}`, data),
  delete: (id: number) => api.delete(`/devices/${id}`),
  // 维护计划
  getMaintenancePlan: (id: number) => api.get(`/devices/${id}/maintenance-plan`),
  updateMaintenancePlan: (id: number, data: Record<string, unknown>) => api.put(`/devices/${id}/maintenance-plan`, data),
  getMaintenanceRecords: (id: number, params?: Record<string, unknown>) => api.get(`/devices/${id}/maintenance-records`, { params }),
  getMaintenanceDue: (daysAhead?: number) => api.get('/devices/maintenance-due', { params: { days_ahead: daysAhead } }),
  runMaintenanceCheck: () => api.post('/devices/run-maintenance-check'),
  // 设备配置
  getConfig: (id: number) => api.get(`/devices/${id}/config`),
  updateConfig: (id: number, data: Record<string, unknown>) => api.put(`/devices/${id}/config`, data),
  // 2026-10-09 丁哥：参数下发/校验（设备管理 & 运维平台共用）
  dispatchConfig: (id: number) => api.post(`/devices/${id}/config/dispatch`),
  verifyConfig: (id: number) => api.post(`/devices/${id}/config/verify`),
  // 固件升级（OTA）
  firmware: {
    check: (id: number) => api.get(`/devices/${id}/firmware`),
    upgrade: (id: number, data: { target_version: string; url?: string; force?: boolean }) =>
      api.post(`/devices/${id}/firmware/upgrade`, data),
    status: (id: number) => api.get(`/devices/${id}/firmware/status`),
  },
};

export const alarmAPI = {
  list: (params?: Record<string, unknown>) => api.get<PaginatedData<Alarm>>('/alarms', { params }),
  get: (id: number) => api.get(`/alarms/${id}`),
  ack: (id: number | string) => api.put(`/alarms/${id}/ack`),
  resolve: (id: number | string) => api.put(`/alarms/${id}/resolve`),
  ignore: (id: number) => api.put(`/alarms/${id}/ignore`),
  del: (id: number) => api.delete(`/alarms/${id}`),
  stats: () => api.get('/alarms/stats/summary'),
  // 告警规则
  rules: {
    list: (params?: unknown) => api.get('/alarm-rules', { params }),
    get: (id: number) => api.get(`/alarm-rules/${id}`),
    create: (data: Record<string, unknown>) => api.post('/alarm-rules', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/alarm-rules/${id}`, data),
    del: (id: number) => api.delete(`/alarm-rules/${id}`),
    toggle: (id: number) => api.put(`/alarm-rules/${id}/toggle`),
    evaluate: (id: number) => api.post(`/alarm-rules/${id}/evaluate`),
  },
  // 规则触发日志
  ruleLogs: (params?: any) => api.get('/alarms/rule-logs', { params }),
};

export const workorderAPI = {
  // params 可选 team_id（卡 2285f54a：admin 按团队过滤，供 Tenants TeamDataView）
  list: (params?: Record<string, unknown>) => api.get<PaginatedData<WorkOrder>>('/work-orders', { params }),
  get: (id: number | string) => api.get<WorkOrder>(`/work-orders/${id}`),
  create: (data: WorkOrderCreateRequest) => api.post<WorkOrder>('/work-orders', data),
  dispatch: (id: number) => api.post(`/work-orders/${id}/dispatch`),
  accept: (id: number | string) => api.post(`/work-orders/${id}/accept`),
  start: (id: number | string) => api.post(`/work-orders/${id}/start`),
  complete: (id: number | string, data: { solution?: string; fault_reason?: string; parts_replaced?: string; photos?: string[] }) => api.post(`/work-orders/${id}/complete`, data),
  verify: (id: number | string) => api.post(`/work-orders/${id}/verify`),
  reject: (id: number | string, reason: string) => api.post(`/work-orders/${id}/reject`, null, { params: { reason } }),
  transfer: (id: number | string, data: { target_engineer_id: number; reason?: string }) => api.post(`/work-orders/${id}/transfer`, data),
  urge: (id: number | string, message?: string) => api.post(`/work-orders/${id}/urge`, { message: message || '请尽快处理' }),
  logs: (id: number | string) => api.get(`/work-orders/${id}/logs`),
  stats: (params?: { start_date?: string; end_date?: string; group_by?: string }) => api.get('/work-orders/stats', { params }),
  // 到场签到（GPS定位 + 备注 + 照片）
  checkin: (id: number | string, data: { latitude?: number; longitude?: number; address?: string; note?: string; photo_url?: string }) =>
    api.post(`/work-orders/${id}/checkin`, data),
  // 申请支援（远程协助 / 高级工程师协助）
  support: (id: number | string, data: { target_engineer_id?: number; reason: string; remote?: boolean }) =>
    api.post(`/work-orders/${id}/support`, data),
  // 申请备件
  requestParts: (id: number | string, data: { part_name: string; part_model?: string; quantity: number; reason: string }) =>
    api.post(`/work-orders/${id}/spare-parts`, data),
  // 验收评价（响应速度 / 维修质量 / 服务态度 三维度星级 + 文字）
  rate: (id: number | string, data: { response_rating: number; quality_rating: number; attitude_rating: number; comment?: string }) =>
    api.post(`/work-orders/${id}/rate`, data),
};

// knowledgeAPI 统一从 ./knowledge re-export（完整超集，含 search/createCategory/updateCategory/deleteCategory）
export { faqAPI, docAPI, knowledgeAPI } from './knowledge';

export const statsAPI = {
  overview: () => api.get('/stats/overview'),
};

// Phase48: 数据大屏独立展示模式
export const dashboardAPI = {
  largeScreen: () => api.get('/dashboard/large-screen'),
};

// 平台监控 — 服务拓扑 + 设备接入统计
export const platformMonitorAPI = {
  topology: () => api.get('/platform/topology'),
  deviceAccessStats: () => api.get('/platform/device-access-stats'),
};

export const monitorAPI = {
  realtime: () => api.get('/monitor/realtime'),
  history: (range: Record<string, unknown>) => api.get('/monitor/history', { params: range }),
};

export const healthAPI = {
  list: () => api.get('/health/devices'),
  trend: (deviceId: number) => api.get(`/health/trend/${deviceId}`),
};

export const rbacAPI = {
  roles: () => api.get('/rbac/roles'),
  getRole: (roleId: number) => api.get(`/rbac/roles/${roleId}`),
  createRole: (data: Record<string, unknown>) => api.post('/rbac/roles', data),
  updateRole: (roleId: number, data: Record<string, unknown>) => api.put(`/rbac/roles/${roleId}`, data),
  deleteRole: (roleId: number) => api.delete(`/rbac/roles/${roleId}`),
  permissions: () => api.get('/rbac/permissions'),
  rbacUsers: (params?: { page?: number; page_size?: number }) => api.get('/rbac/users', { params }),
  rbacUser: (userId: number) => api.get(`/rbac/users/${userId}`),
  updateUserRole: (userId: number, data: Record<string, unknown>) => api.put(`/rbac/users/${userId}/role`, data),
  checkPermission: (permission: string) => api.get(`/rbac/check/${permission}`),
};

// 角色管理 API (团队级 /teams/roles 页面使用)
export const rolesAPI = {
  list: () => api.get('/roles'),
  get: (id: number) => api.get(`/roles/${id}`),
  create: (data: Record<string, unknown>) => api.post('/roles', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/roles/${id}`, data),
  delete: (id: number) => api.delete(`/roles/${id}`),
  permissionsTree: () => api.get('/roles/tree'),
};

export const userAPI = {
  list: () => api.get('/users'),
  get: (id: number) => api.get(`/users/${id}`),
  create: (data: UserCreateRequest) => api.post<User>('/users', data),
  update: (id: number, data: UserUpdateRequest) => api.put<User>(`/users/${id}`, data),
  delete: (id: number) => api.delete(`/users/${id}`),
  // 获取工程师列表（用于转单）
  engineers: () => api.get('/users', { params: { role: 'engineer' } }),
};

export const teamAPI = {
  list: () => api.get('/teams'),
  get: (id: number) => api.get(`/teams/${id}`),
  create: (data: Record<string, unknown>) => api.post('/teams', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/teams/${id}`, data),
  delete: (id: number) => api.delete(`/teams/${id}`),
  members: (teamId: number) => api.get(`/teams/${teamId}/members`),
  addMember: (teamId: number, data: any) => api.post(`/teams/${teamId}/members`, data),
  removeMember: (teamId: number, memberId: number) => api.delete(`/teams/${teamId}/members/${memberId}`),
};

// 工程师管理 API (Teams/Engineers 页面)
export const engineerAPI = {
  list: (params?: Record<string, unknown>) => api.get('/engineers', { params }),
  create: (data: Record<string, unknown>) => api.post('/engineers', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/engineers/${id}`, data),
  delete: (id: number) => api.delete(`/engineers/${id}`),
};

export const gatewayAPI = {
  list: () => api.get('/gateways'),
  get: (id: number) => api.get(`/gateways/${id}`),
  sn: () => api.get('/gateways/sn'),
  generateSn: (data: Record<string, unknown>) => api.post('/gateways/sn/generate', data),
  firmware: () => api.get('/gateways/firmware'),
  uploadFirmware: (formData: FormData) => api.post('/gateways/firmware/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  } as never),
  releaseFirmware: (id: number) => api.post(`/gateways/firmware/${id}/release`),
  upgradeTasks: () => api.get('/gateways/upgrade-tasks'),
  create: (data: GatewayCreateRequest) => api.post<Gateway>('/gateways', data),
  update: (id: number, data: GatewayUpdateRequest) => api.put<Gateway>(`/gateways/${id}`, data),
  delete: (id: number) => api.delete(`/gateways/${id}`),
};

// 遥测数据 API
export const telemetryAPI = {
  report: (data: Record<string, unknown>) => api.post('/telemetry/report', data),
  latest: (deviceId: number) => api.get(`/telemetry/device/${deviceId}/latest`),
  history: (deviceId: number, params?: Record<string, unknown>) => api.get(`/telemetry/device/${deviceId}/history`, { params }),
  stats: (deviceId: number) => api.get(`/telemetry/device/${deviceId}/stats`),
  stationOverview: (stationId: number) => api.get(`/telemetry/station/${stationId}/overview`),
  simulate: (deviceId: number) => api.post(`/telemetry/device/${deviceId}/simulate`),
};

// 故障诊断 API
export const faultDiagnosisAPI = {
  faultCodes: (params?: Record<string, unknown>) => api.get('/fault-diagnosis/fault-codes', { params }),
  getFaultCode: (faultCode: string) => api.get(`/fault-diagnosis/fault-codes/${faultCode}`),
  alarmDiagnosis: (data: Record<string, unknown>) => api.post('/fault-diagnosis/alarm-diagnosis', data),
  quickDiagnosis: (data: Record<string, unknown>) => api.post('/fault-diagnosis/quick-diagnosis', data),
  remoteFix: (data: Record<string, unknown>) => api.post('/fault-diagnosis/remote-fix-attempt', data),
  faultStatistics: () => api.get('/fault-diagnosis/fault-statistics'),
  initFaultCodes: () => api.post('/fault-diagnosis/init-fault-codes'),
};

// 扫码报修 API
export const scanAPI = {
  reportDevice: (data: Record<string, unknown>) => api.post('/scan/device', data),
  quickRepair: (data: Record<string, unknown>) => api.post('/scan/quick-repair', data),
  generateQRCode: (data: Record<string, unknown>) => api.post('/scan/qrcode/generate', data),
  getQRCode: (deviceId: number) => api.get(`/scan/qrcode/${deviceId}`),
  listQRCodes: () => api.get('/scan/qrcodes'),
  deleteQRCode: (deviceId: number) => api.delete(`/scan/qrcode/${deviceId}`),
};

// 远程控制 API
export const remoteAPI = {
  control: (deviceId: number, data: Record<string, unknown>) => api.post(`/devices/${deviceId}/control`, data),
  history: (deviceId: number) => api.get(`/devices/${deviceId}/control-history`),
};

// 告警通知 API
export const alarmNoticeAPI = {
  list: (params?: Record<string, unknown>) => api.get('/alarm-notices', { params }),
  markRead: (id: number) => api.put(`/alarm-notices/${id}/read`),
  resolve: (id: number, handle_desc?: string) => {
    const params: any = {};
    if (handle_desc) params.handle_desc = handle_desc;
    return api.put(`/alarm-notices/${id}/resolve`, null, { params });
  },
  ignore: (id: number) => api.put(`/alarm-notices/${id}/ignore`),
  stats: () => api.get('/alarm-notices/stats'),
  markAllRead: () => api.put('/alarm-notices/read-all'),
};

// AI日志分析 API
// 通知规则配置 API
export const notificationRuleAPI = {
  list: () => api.get('/notification-rules'),
  get: (id: number) => api.get(`/notification-rules/${id}`),
  create: (data: Record<string, unknown>) => api.post('/notification-rules', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/notification-rules/${id}`, data),
  delete: (id: number) => api.delete(`/notification-rules/${id}`),
  toggle: (id: number) => api.put(`/notification-rules/${id}/toggle`),
};

// 平台管理 - 运维团队 API
export const tenantAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; status?: string; type?: string }) =>
    api.get('/tenants', { params }),
  get: (id: number) => api.get(`/tenants/${id}`),
  create: (data: Record<string, unknown>) => api.post('/tenants', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/tenants/${id}`, data),
  delete: (id: number) => api.delete(`/tenants/${id}`),
  stats: () => api.get('/tenants/stats/summary'),
  tenantStats: (id: number) => api.get(`/tenants/${id}/stats`),
  users: (id: number, params?: { page?: number; page_size?: number }) =>
    api.get(`/tenants/${id}/users`, { params }),
};
// 车队（Enterprise）管理 API — /api/v1/enterprises
export const enterpriseAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; status?: string }) =>
    api.get('/enterprises', { params }),
  get: (id: number) => api.get(`/enterprises/${id}`),
  create: (data: Record<string, unknown>) => api.post('/enterprises', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/enterprises/${id}`, data),
  delete: (id: number) => api.delete(`/enterprises/${id}`),
  // 场站绑定（卡691532f2：写入口迁至运维侧，运营商角色操作）
  stations: (id: number) => api.get(`/enterprises/${id}/stations`),
  availableStations: (id: number) => api.get(`/enterprises/${id}/available-stations`),
  setStations: (id: number, stationIds: number[]) =>
    api.put(`/enterprises/${id}/stations`, { station_ids: stationIds }),
};

// 平台管理 - 设备协议 API（暂无后端，使用mock数据）
export const protocolAPI = {
  list: (params?: Record<string, unknown>) => api.get('/device-protocols', { params }),
  get: (id: number) => api.get(`/device-protocols/${id}`),
  create: (data: Record<string, unknown>) => api.post('/device-protocols', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/device-protocols/${id}`, data),
  delete: (id: number) => api.delete(`/device-protocols/${id}`),
};

// 设备库模板 API
export const deviceLibraryAPI = {
  list: (params?: Record<string, unknown>) => api.get('/device-library', { params }),
  get: (id: number) => api.get(`/device-library/${id}`),
  create: (data: Record<string, unknown>) => api.post('/device-library', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/device-library/${id}`, data),
  delete: (id: number) => api.delete(`/device-library/${id}`),
};

export const logAnalysisAPI = {
  // 手动日志分析 POST /log-analysis/analyze
  analyze: (data: { device_id: number; logs: string[]; fault_code?: string; fault_description?: string }) =>
    api.post<{ record_id: number; analysis: Record<string, unknown> | null; error: string | null; model_used?: string; duration_ms?: number }>(
      '/log-analysis/analyze', data),
  // 诊断历史列表 GET /log-analysis（page/page_size/status/device_id）
  list: (params?: { page?: number; page_size?: number; status?: string; device_id?: number }) =>
    api.get<PaginatedData<any>>('/log-analysis', { params }),
  // 诊断详情 GET /log-analysis/{analysis_id}
  get: (id: number) => api.get<Record<string, any>>(`/log-analysis/${id}`),
  // 告警关联诊断 GET /log-analysis/alarm/{alarm_id}
  alarmAnalysis: (alarmId: number) => api.get(`/log-analysis/alarm/${alarmId}`),
  // AI 模型配置
  getModelConfig: () => api.get('/log-analysis/model_config'),
  updateModelConfig: (providers: Array<Record<string, unknown>>) => api.post('/log-analysis/model_config', providers),
  getTaskMappings: () => api.get('/log-analysis/model_config/task-mappings'),
  updateTaskMapping: (data: { task_type: string; model_name: string }) =>
    api.put('/log-analysis/model_config/task-mapping', data),
};

// 值班排班管理 API (Phase9 #52)
export const onCallAPI = {
  rules: {
    list: (params?: Record<string, unknown>) => api.get('/on-call/rules', { params }),
    get: (id: number) => api.get(`/on-call/rules/${id}`),
    create: (data: Record<string, unknown>) => api.post('/on-call/rules', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/on-call/rules/${id}`, data),
    delete: (id: number) => api.delete(`/on-call/rules/${id}`),
    generateShifts: (id: number, params?: Record<string, unknown>) => api.post(`/on-call/rules/${id}/generate-shifts`, null, { params }),
  },
  shifts: {
    list: (params?: Record<string, unknown>) => api.get('/on-call/shifts', { params }),
    getCurrent: (params?: Record<string, unknown>) => api.get('/on-call/shifts/current', { params }),
    create: (data: Record<string, unknown>) => api.post('/on-call/shifts', data),
    updateStatus: (id: number, status: string) => api.put(`/on-call/shifts/${id}`, null, { params: { status } }),
  },
  logs: {
    list: (params?: Record<string, unknown>) => api.get('/on-call/logs', { params }),
    create: (data: Record<string, unknown>) => api.post('/on-call/logs', data),
  },
  stats: {
    getStats: (days?: number) => api.get('/on-call/stats', { params: { days } }),
  },
};

// 操作日志/审计日志 API
export const operationLogAPI = {
  list: (params?: Record<string, unknown>) => api.get('/operation-log', { params }),
  stats: () => api.get('/operation-log/stats'),
};

// 安全管理 API
export const securityAPI = {
  logs: (params?: Record<string, unknown>) => api.get('/security/logs', { params }),
  stats: () => api.get('/security/stats'),
};

// 能耗分析报表 API (Phase9 #54)
export const energyReportAPI = {
  trend: (params?: Record<string, unknown>) => api.get('/energy/trend', { params }),
  summary: (params?: Record<string, unknown>) => api.get('/energy/summary', { params }),
  stationCompare: (params?: Record<string, unknown>) => api.get('/energy/station-compare', { params }),
};

// 报告管理 API
export const reportAPI = {
  list: (params?: { page?: number; page_size?: number; type?: string; status?: string; keyword?: string; station_id?: number }) =>
    api.get('/report-mgmt', { params }),
  get: (id: number) => api.get(`/report-mgmt/${id}`),
  create: (data: Record<string, unknown>) => api.post('/report-mgmt', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/report-mgmt/${id}`, data),
  delete: (id: number) => api.delete(`/report-mgmt/${id}`),
  stats: () => api.get('/report-mgmt/stats/summary'),
};

// ─── 数据操作/密码重置/忘记密码 (卡 922b2fba, 2026-10-08 丁哥需求) ───
/** 平台数据导出/备份（blob 文件流，配合 utils/download 保存） */
export const dataOpsAPI = {
  export: (params: { scope: 'platform' | 'tenant'; tenant_id?: number; mode?: 'export' | 'backup' }) =>
    api.get('/admin-data/export', { params, responseType: 'blob' }),
};

/** 管理员重置用户密码：不传 new_password 则后端生成一次性临时密码返回 */
export const passwordResetAPI = {
  user: (userId: number, body?: { new_password?: string }) =>
    api.post(`/users/${userId}/reset-password`, body || {}),
  tenantUser: (tenantId: number, userId: number, body?: { new_password?: string }) =>
    api.post(`/tenants/${tenantId}/users/${userId}/reset-password`, body || {}),
};

/** 忘记密码：提交申请（不泄露账号存在性）+ 管理员处理队列 */
export const forgotPasswordAPI = {
  submit: (account: string) => api.post('/auth/forgot-password', { account }),
  requests: () => api.get('/auth/forgot-password/requests'),
  resolve: (id: number) => api.post(`/auth/forgot-password/requests/${id}/resolve`),
};

// 协议实例管理 API (Phase33)
export const protocolInstanceAPI = {
  list: (params?: Record<string, unknown>) => api.get('/protocol-instances', { params }),
  get: (id: number) => api.get(`/protocol-instances/${id}`),
  create: (data: Record<string, unknown>) => api.post('/protocol-instances', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/protocol-instances/${id}`, data),
  delete: (id: number) => api.delete(`/protocol-instances/${id}`),
  connect: (id: number) => api.post(`/protocol-instances/${id}/connect`),
  disconnect: (id: number) => api.post(`/protocol-instances/${id}/disconnect`),
};

// 解析器配置 API (Phase33)
export const parserConfigAPI = {
  list: (params?: Record<string, unknown>) => api.get('/parser-configs', { params }),
  create: (data: Record<string, unknown>) => api.post('/parser-configs', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/parser-configs/${id}`, data),
  delete: (id: number) => api.delete(`/parser-configs/${id}`),
};

// 连接状态仪表板 API (Phase33)
export const connectionDashboardAPI = {
  get: () => api.get('/connection-dashboard'),
};

// 数字孪生可视化 API (Phase10 #55)
export const digitalTwinAPI = {
  models: {
    list: (params?: Record<string, unknown>) => api.get('/digital-twin/models', { params }),
    get: (id: number) => api.get(`/digital-twin/models/${id}`),
    create: (data: Record<string, unknown>) => api.post('/digital-twin/models', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/digital-twin/models/${id}`, data),
    delete: (id: number) => api.delete(`/digital-twin/models/${id}`),
  },
  scenes: {
    list: (params?: Record<string, unknown>) => api.get('/digital-twin/scenes', { params }),
    get: (id: number) => api.get(`/digital-twin/scenes/${id}`),
    create: (data: Record<string, unknown>) => api.post('/digital-twin/scenes', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/digital-twin/scenes/${id}`, data),
    delete: (id: number) => api.delete(`/digital-twin/scenes/${id}`),
  },
  dataPoints: {
    list: (params?: Record<string, unknown>) => api.get('/digital-twin/data-points', { params }),
    create: (data: Record<string, unknown>) => api.post('/digital-twin/data-points', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/digital-twin/data-points/${id}`, data),
    delete: (id: number) => api.delete(`/digital-twin/data-points/${id}`),
  },
  // 快捷方法（async/await：错误向上抛，由调用方 try/catch 处理）
  listScenes: async () => (await api.get('/digital-twin/scenes')).data,
  getSceneLayout: async (sceneId: number) => (await api.get(`/digital-twin/scenes/${sceneId}/layout`)).data,
  getRealtime: async (stationId?: number) => (await api.get('/digital-twin/realtime', { params: { station_id: stationId } })).data,
  initDefault: async (stationId: number) => (await api.post('/digital-twin/init-default', null, { params: { station_id: stationId } })).data,
};

// V2G 调度 API
export const v2gAPI = {
  dispatch: (deviceId: number, data: { dispatch_type: string; target_power_kw: number }) =>
    api.post(`/devices/${deviceId}/v2g/dispatch`, data),
  dispatchHistory: (deviceId: number) =>
    api.get(`/devices/${deviceId}/v2g/dispatch/history`),
};

// 运行效率报表 API (Phase48)
export const efficiencyAPI = {
  // 设备利用率报告
  utilization: (params?: Record<string, unknown>) => api.get('/reports/utilization', { params }),
  // 充放电效率报告
  efficiency: (params?: Record<string, unknown>) => api.get('/reports/efficiency', { params }), 
  // 发电效率报告
  generation: (params?: Record<string, unknown>) => api.get('/reports/generation', { params }), 
  // 故障分析报告
  faults: (params?: Record<string, unknown>) => api.get('/reports/faults', { params }),
  // V2G运营报表
  v2g: (params?: Record<string, unknown>) => api.get('/reports/v2g', { params }),
  // 单设备效率详情
  deviceEfficiency: (deviceId: number) => api.get(`/devices/${deviceId}/efficiency`),
};

// 巡检运维管理 API
export const inspectionAPI = {
  // 计划
  plans: {
    list: (params?: Record<string, unknown>) => api.get('/inspection/plans', { params }),
    get: (id: number) => api.get(`/inspection/plans/${id}`),
    create: (data: Record<string, unknown>) => api.post('/inspection/plans', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/inspection/plans/${id}`, data),
    delete: (id: number) => api.delete(`/inspection/plans/${id}`),
    toggleStatus: (id: number, status: string) => api.put(`/inspection/plans/${id}/status`, null, { params: { status } }),
  },
  // 任务
  tasks: {
    list: (params?: Record<string, unknown>) => api.get('/inspection/tasks', { params }),
    get: (id: number) => api.get(`/inspection/tasks/${id}`),
    create: (data: Record<string, unknown>) => api.post('/inspection/tasks', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/inspection/tasks/${id}`, data),
    delete: (id: number) => api.delete(`/inspection/tasks/${id}`),
  },
  // 统计
  stats: () => api.get('/inspection/stats'),
  // 巡检模板（inspection_templates）
  templates: {
    list: (params?: Record<string, unknown>) => api.get('/inspection/templates', { params }),
    get: (id: number) => api.get(`/inspection/templates/${id}`),
    create: (data: Record<string, unknown>) => api.post('/inspection/templates', data),
    update: (id: number, data: Record<string, unknown>) => api.put(`/inspection/templates/${id}`, data),
    delete: (id: number) => api.delete(`/inspection/templates/${id}`),
  },
  // 巡检结果（inspection_results，按任务录入）
  results: {
    list: (taskId: number, params?: Record<string, unknown>) => api.get(`/inspection/tasks/${taskId}/results`, { params }),
    create: (taskId: number, data: Record<string, unknown>) => api.post(`/inspection/tasks/${taskId}/results`, data),
  },
};

// 运营平台 - 互联互通 + 市政监管 (SPEC §2.5) — 迁移至 ./operateExternal.ts
export {
  interconnectAPI,
  interconnectOrderAPI,
  supervisionAPI,
  regulatoryReportAPI,
  complianceAPI,
} from './operateExternal';

// 系统配置 - 全局配置/支付通道/发票配置 (admin spec §2.3)
export const globalConfigAPI = {
  get: () => api.get('/system-config/global'),
  update: (data: Record<string, unknown>) => api.put('/system-config/global', data),
};

export const paymentChannelAPI = {
  list: () => api.get('/system-config/payment-channels'),
  create: (data: Record<string, unknown>) => api.post('/system-config/payment-channels', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/system-config/payment-channels/${id}`, data),
  delete: (id: number) => api.delete(`/system-config/payment-channels/${id}`),
};

export const invoiceConfigAPI = {
  get: () => api.get('/system-config/invoice'),
  update: (data: Record<string, unknown>) => api.put('/system-config/invoice', data),
};
