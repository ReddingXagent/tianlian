import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type {
  LoginResponse,
  SendCodeResponse,
  WorkOrder,
  WorkOrderProgress,
  KnowledgeItem,
  Engineer,
  WorkStats,
  Notification,
  ApiResponse,
  V2GDevice,
  V2GEfficiency,
  V2GEfficiencyTrend,
  V2GDispatch,
  EfficiencyRecord,
} from '../types';

// API 基础 URL
const API_BASE_URL = 'http://demo.example.com/api/v1';

// 创建 axios 实例
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token 存储 Key
const TOKEN_KEY = 'engineer_token';
const ENGINEER_KEY = 'engineer_info';

// 请求拦截器 - 添加 token
api.interceptors.request.use(
  async (config) => {
    const token = await AsyncStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token过期，清除登录信息
      await AsyncStorage.multiRemove([TOKEN_KEY, ENGINEER_KEY]);
    }
    return Promise.reject(error);
  }
);

// ============ 认证相关 API ============

export const authApi = {
  // 发送验证码
  sendCode: async (phone: string): Promise<SendCodeResponse> => {
    const response = await api.post<ApiResponse<SendCodeResponse>>('/auth/send-code', { phone });
    return response.data.data;
  },

  // 手机号验证码登录
  loginByCode: async (phone: string, code: string): Promise<LoginResponse> => {
    const response = await api.post<ApiResponse<LoginResponse>>('/auth/login-code', { phone, code });
    const { token, engineer } = response.data.data;
    await AsyncStorage.setItem(TOKEN_KEY, token);
    await AsyncStorage.setItem(ENGINEER_KEY, JSON.stringify(engineer));
    return response.data.data;
  },

  // 账号密码登录
  loginByPassword: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<ApiResponse<LoginResponse>>('/auth/login', { username, password });
    const { token, engineer } = response.data.data;
    await AsyncStorage.setItem(TOKEN_KEY, token);
    await AsyncStorage.setItem(ENGINEER_KEY, JSON.stringify(engineer));
    return response.data.data;
  },

  // 退出登录
  logout: async () => {
    try {
      await api.post('/auth/logout');
    } catch (e) {
      // 忽略错误
    }
    await AsyncStorage.multiRemove([TOKEN_KEY, ENGINEER_KEY]);
  },

  // 获取当前工程师信息
  getCurrentEngineer: async (): Promise<Engineer | null> => {
    const engineerStr = await AsyncStorage.getItem(ENGINEER_KEY);
    return engineerStr ? JSON.parse(engineerStr) : null;
  },

  // 检查登录状态
  isLoggedIn: async (): Promise<boolean> => {
    const token = await AsyncStorage.getItem(TOKEN_KEY);
    return !!token;
  },
};

// ============ 工单相关 API ============

export const workOrderApi = {
  // 获取工作统计
  getStats: async (): Promise<WorkStats> => {
    const response = await api.get<ApiResponse<WorkStats>>('/engineer/work-orders/stats');
    return response.data.data;
  },

  // 获取待接单列表
  getPendingList: async (): Promise<WorkOrder[]> => {
    const response = await api.get<ApiResponse<WorkOrder[]>>('/engineer/work-orders/pending');
    return response.data.data;
  },

  // 获取进行中列表
  getProcessingList: async (): Promise<WorkOrder[]> => {
    const response = await api.get<ApiResponse<WorkOrder[]>>('/engineer/work-orders/processing');
    return response.data.data;
  },

  // 获取工单详情
  getDetail: async (id: string): Promise<WorkOrder> => {
    const response = await api.get<ApiResponse<WorkOrder>>(`/engineer/work-orders/${id}`);
    return response.data.data;
  },

  // 接单
  accept: async (id: string): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/accept`);
  },

  // 转单
  transfer: async (id: string, reason: string): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/transfer`, { reason });
  },

  // 到场确认
  arrive: async (id: string): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/arrive`);
  },

  // 记录进度
  recordProgress: async (id: string, data: { description: string; photos?: string[] }): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/progress`, data);
  },

  // 申请支援
  requestSupport: async (id: string, description: string): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/support`, { description });
  },

  // 申请备件
  requestParts: async (id: string, data: { name: string; quantity: number; reason: string }): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/parts`, data);
  },

  // 完成工单
  complete: async (id: string, data: {
    faultReason: string;
    solution: string;
    replacedParts?: string;
    photos?: string[];
  }): Promise<void> => {
    await api.post(`/engineer/work-orders/${id}/complete`, data);
  },

  // 获取进度记录
  getProgressList: async (id: string): Promise<WorkOrderProgress[]> => {
    const response = await api.get<ApiResponse<WorkOrderProgress[]>>(`/engineer/work-orders/${id}/progress`);
    return response.data.data;
  },
};

// ============ 知识库相关 API ============

export const knowledgeApi = {
  // 获取故障案例列表
  getFaultCases: async (keyword?: string): Promise<KnowledgeItem[]> => {
    const params = keyword ? { keyword } : {};
    const response = await api.get<ApiResponse<KnowledgeItem[]>>('/knowledge/fault-cases', { params });
    return response.data.data;
  },

  // 获取维修手册列表
  getManuals: async (keyword?: string): Promise<KnowledgeItem[]> => {
    const params = keyword ? { keyword } : {};
    const response = await api.get<ApiResponse<KnowledgeItem[]>>('/knowledge/manuals', { params });
    return response.data.data;
  },

  // 搜索知识库
  search: async (keyword: string): Promise<KnowledgeItem[]> => {
    const response = await api.get<ApiResponse<KnowledgeItem[]>>('/knowledge/search', {
      params: { keyword },
    });
    return response.data.data;
  },

  // 获取详情
  getDetail: async (id: string): Promise<KnowledgeItem> => {
    const response = await api.get<ApiResponse<KnowledgeItem>>(`/knowledge/${id}`);
    return response.data.data;
  },
};

// ============ 个人中心 API ============

export const profileApi = {
  // 获取个人信息
  getProfile: async (): Promise<Engineer> => {
    const response = await api.get<ApiResponse<Engineer>>('/engineer/profile');
    return response.data.data;
  },

  // 更新个人信息
  updateProfile: async (data: Partial<Engineer>): Promise<void> => {
    await api.put('/engineer/profile', data);
  },

  // 获取消息列表
  getNotifications: async (): Promise<Notification[]> => {
    const response = await api.get<ApiResponse<Notification[]>>('/engineer/notifications');
    return response.data.data;
  },

  // 标记消息已读
  markNotificationRead: async (id: string): Promise<void> => {
    await api.put(`/engineer/notifications/${id}/read`);
  },

  // 获取未读消息数量
  getUnreadCount: async (): Promise<number> => {
    const response = await api.get<ApiResponse<{ count: number }>>('/engineer/notifications/unread-count');
    return response.data.data.count;
  },
};

// ============ V2G 设备相关 API ============

export const v2gApi = {
  // 获取 V2G 设备列表
  getDevices: async (): Promise<V2GDevice[]> => {
    const response = await api.get<ApiResponse<V2GDevice[]>>('/devices', {
      params: { type: 'v2g_charger' },
    });
    return response.data.data;
  },

  // 获取设备效率详情
  getEfficiency: async (deviceId: string): Promise<V2GEfficiency> => {
    const response = await api.get<ApiResponse<V2GEfficiency>>(`/devices/${deviceId}/efficiency`);
    return response.data.data;
  },

  // 获取设备效率趋势
  getEfficiencyTrend: async (deviceId: string): Promise<V2GEfficiencyTrend[]> => {
    const response = await api.get<ApiResponse<V2GEfficiencyTrend[]>>(
      `/devices/${deviceId}/efficiency/trend`
    );
    return response.data.data;
  },

  // 发送调度指令
  dispatch: async (deviceId: string, data: {
    type: string;
    targetPower: number;
    targetDuration: number;
  }): Promise<void> => {
    await api.post(`/devices/${deviceId}/v2g/dispatch`, data);
  },

  // 获取调度列表（待执行）
  getPendingDispatches: async (): Promise<V2GDispatch[]> => {
    const response = await api.get<ApiResponse<V2GDispatch[]>>('/v2g/dispatch/pending');
    return response.data.data;
  },

  // 确认执行调度
  confirmDispatch: async (dispatchId: string): Promise<void> => {
    await api.post(`/v2g/dispatch/${dispatchId}/confirm`);
  },

  // 拒绝调度
  rejectDispatch: async (dispatchId: string, reason: string): Promise<void> => {
    await api.post(`/v2g/dispatch/${dispatchId}/reject`, { reason });
  },

  // 获取调度历史
  getDispatchHistory: async (): Promise<V2GDispatch[]> => {
    const response = await api.get<ApiResponse<V2GDispatch[]>>('/v2g/dispatch/history');
    return response.data.data;
  },

  // 提交效率检测记录
  submitEfficiency: async (deviceId: string, data: {
    inputEnergy: number;
    outputEnergy: number;
    measurementType: string;
  }): Promise<EfficiencyRecord> => {
    const response = await api.post<ApiResponse<EfficiencyRecord>>(
      `/devices/${deviceId}/efficiency`,
      data
    );
    return response.data.data;
  },

  // 获取效率检测历史
  getEfficiencyHistory: async (deviceId: string): Promise<EfficiencyRecord[]> => {
    const response = await api.get<ApiResponse<EfficiencyRecord[]>>(
      `/devices/${deviceId}/efficiency/history`
    );
    return response.data.data;
  },
};

export default api;