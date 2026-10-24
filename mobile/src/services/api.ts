import axios from 'axios';
import { env } from '../config/env';

// 创建 axios 实例（出站点统一收敛在 src/config/env.ts）
export const api = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器 - 添加 token
api.interceptors.request.use(
  (config) => {
    // TODO: 从安全存储获取 token
    // const token = await SecureStore.getItemAsync('token');
    const token = null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // 服务器返回错误响应
      console.error('API Error:', error.response.status, error.response.data);
    } else if (error.request) {
      // 请求已发出但无响应 (可能是网络问题)
      console.error('Network Error:', error.request);
    } else {
      console.error('Error:', error.message);
    }
    return Promise.reject(error);
  }
);

// API 方法封装
export const deviceApi = {
  getAll: () => api.get('/devices'),
  getById: (id: string) => api.get(`/devices/${id}`),
  update: (id: string, data: any) => api.put(`/devices/${id}`, data),
  getMaintenanceRecords: (id: string) => api.get(`/devices/${id}/maintenance-records`),
  getEfficiency: (id: string) => api.get(`/devices/${id}/efficiency`),
};

export const reportsApi = {
  getUtilization: () => api.get('/reports/utilization'),
  getEfficiency: () => api.get('/reports/efficiency'),
  getGeneration: () => api.get('/reports/generation'),
};

export const stationApi = {
  // C端只读入口 (契约 §1, /business/stations): 不按 team 隔离, 跨运营商浏览, 信封 code=0
  // lat+lon 同传进入 nearby 模式 (按距离过滤排序 + 携带 distance_km)。返回 {items,total,page,page_size}
  getAll: (params?: {
    lat?: number;
    lon?: number;
    radius?: number;
    keyword?: string;
    city?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/business/stations', { params }),
  getById: (id: string) => api.get(`/business/stations/${id}`),
  // 管理端写操作 (保留 /stations, 需 station 权限 + team 隔离)
  create: (data: any) => api.post('/stations', data),
  update: (id: string, data: any) => api.put(`/stations/${id}`, data),
  delete: (id: string) => api.delete(`/stations/${id}`),
};

export const workOrderApi = {
  getAll: () => api.get('/workorders'),
  getById: (id: string) => api.get(`/workorders/${id}`),
  create: (data: any) => api.post('/workorders', data),
  update: (id: string, data: any) => api.put(`/workorders/${id}`, data),
  delete: (id: string) => api.delete(`/workorders/${id}`),
  urge: (id: string) => api.post(`/workorders/${id}/urge`),
  accept: (id: string, data: { result: string; rating: number; comment?: string }) =>
    api.post(`/workorders/${id}/accept`, data),
};

export const alarmApi = {
  getAll: () => api.get('/alarms'),
  getById: (id: string) => api.get(`/alarms/${id}`),
  confirm: (id: string) => api.post(`/alarms/${id}/confirm`),
  resolve: (id: string) => api.post(`/alarms/${id}/resolve`),
  update: (id: string, data: any) => api.put(`/alarms/${id}`, data),
};

export const statsApi = {
  overview: () => api.get('/stats/overview'),
  healthTrend: () => api.get('/stats/health-trend'),
  alarmStats: () => api.get('/stats/alarm-stats'),
  workOrderStats: () => api.get('/stats/workorder-stats'),
};

export const knowledgeApi = {
  getAll: () => api.get('/knowledge'),
  getById: (id: string) => api.get(`/knowledge/${id}`),
  search: (query: string) => api.get(`/knowledge/search?q=${encodeURIComponent(query)}`),
  create: (data: any) => api.post('/knowledge', data),
  update: (id: string, data: any) => api.put(`/knowledge/${id}`, data),
};

export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  refreshToken: () => api.post('/auth/refresh'),
};

// 运维评价 API
export const evaluationApi = {
  getOverview: () => api.get('/evaluation/overview'),
  getEngineerEvaluations: (engineerId: string) => api.get(`/evaluation/engineer/${engineerId}`),
  create: (data: { engineerId: string; rating: number; comment: string }) =>
    api.post('/evaluation', data),
};

// 用户资料 API
export const profileApi = {
  get: () => api.get('/profile'),
  update: (data: { name?: string; email?: string }) => api.put('/profile', data),
  getNotifications: () => api.get('/profile/notifications'),
};

// 缓存清理工具
export const cacheUtils = {
  clear: async () => {
    // 需要配合 cache 服务实现
    console.log('[Cache] Clearing all cache...');
    return true;
  },
};
